# MCP contract

One authenticated Streamable HTTP endpoint: `http://127.0.0.1:18765/mcp` by default.
The optional stdio adapter only forwards to this endpoint. It does not start Ghidra.
The protocol is implemented with the pinned MCP Python SDK; two independent SDK
clients are included in live validation.

Tools: `service_health`, `session_open`, `session_close`, `job_submit`, `job_status`,
`job_result`, `job_cancel`, `engine_restart`, and `service_stop`.

Open a session and use its opaque `session` for all job calls. Submit an `operation`,
`arguments` object, and optional `timeout_seconds` (0.05–3600, including queue time).
Submission durably records a stable `id` and returns immediately. Status/result take
`session` and `job`. Terminal states are `completed`, `failed`, `timed_out`, and
`cancelled`; other states are `queued` and `running`. A cancellation request can leave
the job running until its monitor is observed. The supervisor does not replay jobs.

Every program operation takes `program`, the exact project pathname returned by
import/open, for example `/small.exe`. Mutations, save, export and close require
`expected_version`, the full restart-unique version string returned with the program.
An old version produces `stale_revision` before mutation. Results include `program`
with binary SHA-256, project, program ID, generation, revision, version, and `durable`.
The numeric revision resets after reopening; compare the full version string.

## Operations

| Operation | Arguments beyond session |
|---|---|
| `capabilities` | `{}`; lists query/edit categories, providers and exporters |
| `project_open` | `name`, optional `directory` (default `runtime/projects`) |
| `project_close` | `{}`; first close all loaded programs |
| `programs` | `{}`; returns loaded identities and on-disk program paths |
| `program_import` | `file`, optional `name`, `folder`, `analyze` (true), `loader`, `language`, `compiler`, `loader_options`, `analysis_options`; optional script pipeline below |
| `program_open` | `path`; repeated opens return the same loaded Program |
| `program_save` | `program`, `expected_version` |
| `program_close` | `program`, `expected_version`, `save` (true); use `save:false, discard:true` to discard volatile edits |
| `decompile` | `program`, `function` (address or unambiguous name), `cache` (true), `coalesce` (true), `decompiler_timeout` (1–300 seconds) |
| `decompile_batch` | Same as decompile, with `functions` array instead of `function`; maximum 64; sequential within one reservation |
| `query` | `program`, `kind`, optional `offset`, `limit` (1–1000), `filter`; category-specific arguments below |
| `edit` | `program`, `expected_version`, `changes` (1–100), `save` (true) |
| `analyze` | `program`, `expected_version`, `all` (true), `analysis_options`, `save` (true) |
| `script` | `program`, `expected_version`, script arguments below, `save` (true) |
| `export` | `program`, `expected_version`, `file`, `format` (exporter name or class name), `options` keyed by actual exporter option names |

Paths must resolve within the checkout, including through filesystem links. The
Ghidra project directory cannot contain a path component starting with a dot; use
`runtime/projects`, not `.local/projects`. The service opens one writable project at
a time. All sessions see the same loaded program set and shared changes. Selecting a
target means supplying its explicit ID; no request depends on GUI focus or hidden
session routing. Program close/reopen is coordinated with queued reads and writes.

## Query categories

`functions`, `strings`, `data`, `symbols`, `namespaces`, `classes`, `imports`,
`exports`, `segments`, `types`, and `analysis_options` support pagination/filtering.
`function`, `disassembly`, and `function_xrefs` require `function`.
`xrefs_to`, `xrefs_from`, and `bytes` require `address`; bytes also accepts `length`
(1–65536). Query output contains `items`, `offset`, and `has_more`.

## Atomic edits

Each item in `changes` has `op`:

| Edit | Required fields |
|---|---|
| `rename_function` | `function`, `name` |
| `rename_data` | `address`, `name` |
| `rename_variable` | `function`, `variable`, `name` |
| `variable_type` | `function`, `variable`, `type` |
| `comment` | `address`, `text`; optional `type`: `EOL`, `PRE`, `POST`, `PLATE`, `REPEATABLE` |
| `prototype` | `function`, `signature` (C prototype, optional semicolon) |
| `define_type` | `declaration` (C struct/union/enum/typedef declaration) |
| `apply_type` | `address`, `type`; optional `clear:true` to replace existing code/data in that type's extent |
| `disassemble` | `address`, optional `length` (1–65536) |
| `create_function` | `address`, `name`; disassemble its bytes first |
| `namespace` | `name` |

Unknown types fail; they are never silently replaced with `int`. A batch uses one
Ghidra transaction. Any failing/cancelled change rolls back the whole batch, reports
`effect:rolled_back`, and preserves the prior version. Success increments the revision,
invalidates result/native caches, and saves by default. Save failure after commit
reports failure with `effect:applied` and `durable:false`; it is not a rolled-back edit.
Automatic analysis is not silently run after atomic edits. Use `analyze` explicitly.

## Script pipeline

Use `name` and `args` for a single script, or `pre_scripts` / `post_scripts` arrays of
`{"name":"Probe.java","args":["value"]}`. `scripts` is an additional ordered
pre-analysis list. Maximum 32 pipeline entries, including the analysis stage.
`analyze` defaults false for `script` and true for `program_import`. Analysis happens
between pre and post scripts, respects `enableHeadlessAnalysis`, and accepts `all`,
`analysis_options` and `analysis_timeout` (default 300 seconds). An analysis-stage
timeout is reported as `analysis_timed_out` and through `analysisTimeoutOccurred`;
the overall job timeout still applies to the entire pipeline.

`paths` lists up to 16 repository-local script directories. Java source, compiled Java
`package.Name.class`, and Jython use actual Ghidra script implementations. Untagged
`.py` defaults to Jython; explicit runtime tags are honored. `properties_paths` lists
directories searched for Ghidra `.properties` inputs. Script arguments also supply
headless `ask*` inputs. `address` and `selection` (array of `[start,end]` pairs) set an
explicit initial script context. If omitted, address is the program minimum and
selection is empty. Nested scripts inherit Ghidra state, controls and property paths.

Headless storage, analysis flags and continuation are shared within one job and reset
between jobs. `ABORT` skips the remaining pipeline. Delete continuations discard an
import before saving; process-mode deletion requires `allow_delete:true`, equivalent
to ordinary headless `-okToDelete`. Import-directory changes affect the imported
program's save path. Script failure stops the pipeline, reports captured stdout/stderr
and `partially_applied`, increments loaded-program versions conservatively, and does
not save automatically. Script success saves all loaded programs by default because
trusted scripts can affect targets beyond their initial currentProgram.

The full Java/Ghidra API remains available to trusted scripts, including additional
loader, export, datatype and analysis options. Scripts are not sandboxed. They must
complete and join any background work before returning, and must not bypass ownership
by launching additional project owners. Persistent JVM globals or external effects
cannot be automatically rolled back. Unsupported provider requests fail explicitly.

## Bounds, cancellation and evidence

Default limits: four read workers, four analyzer CPUs (exclusive with reads), two
loaded programs, 64 queued jobs, 16 outstanding jobs per session, 128 sessions,
30-minute idle-session expiry, 256 retained jobs, 64 cached read records, 1 MiB output
per job, 256 KiB arguments, 4 GiB JVM heap and 6 GiB total owned Windows process memory.
FIFO admission and per-session quotas bound waiting; a queued writer blocks later
read admission. Batches retain their read reservation for the whole batch.

Decompiler leases are exclusive. Result-cache hits and coalesced reads are labeled;
their native timing describes the original computation. A cancelled coalesced follower
does not cancel its producer. Failed/cancelled producers do not propagate cancellation
to another session; a follower can recompute under its own monitor.

Disconnecting a transport does not cancel durable accepted jobs. Explicit session
close or idle expiry requests cancellation and releases output. Compact evidence
remains until bounded global retention evicts it. Completed records live in the local
SQLite journal; client IDs are independent from engine generations. Restart retains
job metadata and reports uncertain writes without replay. Supervisor restart expires
sessions, but its durable journal remains available locally for audit.

Cooperative cancellation affects one monitor. A native crash recovers through the
persistent interface. If cancellation is unobserved for ten seconds, the supervisor
restarts its entire Windows Job Object, waits for owner exit, and reopens last saved
state. Other work can be interrupted. `outcome_unknown` distinguishes that failure
boundary from rollback and ordinary cancellation. Explicit `engine_restart` has the
same shared effect. No process is killed by executable name.

`service_stop` closes the owner and releases its project lock. It does not silently
save volatile changes or uncertain scripts: save desired versions before stopping.
The next start restores the previously open project and targets with new version
tokens. Authentication tokens, logs, caches, settings, projects and journals remain
inside this checkout. Browser Origins and unexpected Host headers are rejected.

## Upstream mapping

Upstream function lookup, decompilation, disassembly, references, strings, data,
symbols, namespaces, imports/exports and segments map to the categories above.
Renames, comments, prototypes and local types map to atomic `edit`. GUI-only
`get_current_address` / `get_current_function` are replaced by explicit program and
address arguments. The legacy HTTP endpoints and GUI plugin are not packaged or
started. This is an intentional API change, not a second operational backend.
