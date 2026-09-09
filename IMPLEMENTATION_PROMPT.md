# Implement a shared-program Ghidra analysis service

Implement this product in the current checkout. Read AGENTS.md and DESIGN_REVIEW.md first and carry
the work through the complete, tested product; do not stop at a design document,
prototype, read-only subset, or first milestone.
Ask me clarifying questions whenever you need product guidance and continue work
that does not depend on the answer.

## Context and repository

This is a fork of LaurieWired/GhidraMCP. Its Java Ghidra plugin and Python MCP
bridge are the entry point. Origin is the user's fork; upstream is the original
repository. The initial checkout is on shared-program-service, based on upstream
commit 27f316f80139e2d5dec882519a1bdf4aa46ac04c.

The user already has an operational Ghidra setup associated with another project.
This new project must remain entirely separate. Do not integrate with, modify, or
retire that setup. Use a dedicated local distribution and synthetic fixtures here.
The fork is public: do not include private binaries, project databases, credentials,
or machine-specific setup files in anything proposed for publication.

## Objective

Provide fast parallel Ghidra access for N independent agent sessions without
duplicating the analyzed project or loading an entire Program/JVM per session.
One service owns the project lock and loads the Program once. Agents submit jobs
to that service. A bounded pool of persistent native decompiler processes serves
requests using separate DecompInterface instances against the shared Program.

Independence means separate jobs, routing, cancellation, and session metadata.
It does not mean each agent has a conflicting private database version. Explain
this limit clearly. More sessions than workers must receive fair, bounded queuing;
N does not imply unlimited simultaneous execution or linear speedup.

## Confirmed scope and delivery

The user clarified: "i prefer a design thst is fast and consolidated so there is
just 1 clean surface on my computer that all agents reach for" and "i dont want
first second third versions i want the full product how i've described it from
the start". This supersedes the earlier optional questions and provisional defaults.

Deliver one persistent headless service, one MCP interface, and one project owner.
All agents connect to that service. Do not create a choice between GUI and headless
backends, parallel installations the user must coordinate, or a second agent-facing
execution path. MCP is the access protocol; a GUI is not needed for this product's
agent analysis workflow. A future human visualization client is outside the agreed
scope and cannot become another project owner or a prerequisite for agent access.

The complete product includes parallel reads, shared edits, function/type creation,
trusted script execution, reanalysis, project/program lifecycle, persistence,
resource controls, cancellation, evidence, local packaging, and validation. Preserve
the useful capabilities of the upstream MCP surface with explicit program identity.
Do not defer these capabilities as future versions. Build in whatever internal order
is effective, but continue until the complete scope is implemented and validated.

The user has not authorized a cutover of the existing setup. Build and demonstrate
the complete product separately; migration or reconfiguration of the existing setup
still requires a later explicit instruction. One new surface is the intended product,
not permission to consolidate the user's current databases during development.

Use your judgment on routine implementation choices. Ask when a remaining choice
materially changes resource use, product behavior, or scope, rather than re-asking
the resolved question of full product versus partial delivery.

## Architecture and behavior

- Audit upstream source and build first. Extract analysis operations from GUI
  selection and HTTP handlers into a reusable service core. A Java service core
  is a natural fit for this fork, but document justified alternatives.
- Pin a supported Ghidra/JDK/toolchain combination using current official sources.
  Do not silently rely on whichever shared installation happens to be present.
- Implement a persistent headless host. Initialize Ghidra and open the fixture
  project once; never launch analyzeHeadless or import/reanalyze per tool request.
- Keep the MCP endpoint/job supervisor outside the sole owning engine JVM, so it
  can report engine failure and recover that owner. This is one managed product
  and one public interface, not a second operational surface or a Program clone.
  Retain bounded durable job metadata across engine restarts. Do not automatically
  replay writes or scripts whose outcome is uncertain. Only one process may own
  a given writable project at any instant, including during recovery.
- Program identity must be explicit. No remote request may depend on a human's
  current GUI tab, address, or selection. Include project/program open, import,
  selection, save, and close operations with safe job coordination. Load each active
  target only once, share it across sessions, and bound the set of loaded targets.
- Give sessions stable opaque IDs and jobs stable IDs. Include submit, status,
  result, and cancel operations for long jobs. Preserve useful existing MCP tools
  where practical and document any incompatible API changes.
- Support decompilation by address/name, disassembly, xrefs, function/string lookup,
  and the upstream symbol, data, namespace, import/export, and segment queries.
  Pool and reuse DecompInterface instances; never lease one to two jobs at once.
  Bound queue length, output size, cache size, worker count, and idle session state.
  Distinguish queued, running, completed, failed, timed-out, and cancelled states.
- Implement a fair service-level read/write gate: concurrent supported reads,
  drain active reads before a write, run a Ghidra transaction, then advance the
  revision and invalidate caches before admitting more reads. Prevent writer
  starvation. Coordinate native decompiler caches as well as result caches.
- This gate is application scheduling, not a replacement for Ghidra's internal
  synchronization. Inspect actual API/thread constraints. Do not assume arbitrary
  Ghidra APIs, scripts, GUI actions, or auto-analysis are safe concurrently.
- All mutation sources, including scripts and background analysis, must participate
  in coordination. Do not claim consistency based only on gating named MCP edits.
  Never open the same writable project in two processes.
- Use a controlled script/analysis execution lane matching the pinned version's
  headless threading assumptions. HeadlessAnalyzer is not thread safe; do not
  dispatch concurrent client requests into that singleton. Account for queued
  domain events, nested analyzeChanges/analyzeAll calls, and actual analyzer
  completion before releasing a write reservation. Do not hold an internal
  database lock while waiting for analyzer threads. Arbitrary scripts that can
  change JVM-global state require an engine-wide exclusive reservation.
- For edits, require an expected program revision or equivalent conflict check.
  Report stale edits instead of silently overwriting newer work. Service-owned
  atomic edits must roll back on failure/cancellation and leave caches coherent.
  Do not extend this guarantee to arbitrary scripts or multi-transaction analysis.
  Report rolled_back, partially_applied, and outcome_unknown explicitly when relevant,
  including program revision and persistence state. Session-local proposals are
  optional metadata; they cannot affect decompilation until applied.
- Include function/data/variable renaming, comments, prototypes, local variable types,
  function creation/disassembly, and reusable datatype definition/application tools.
  Include trusted script execution and explicit reanalysis as coordinated jobs.
  Default scripts to exclusive execution because their effects are not knowable
  from their names. Integrate analysis completion with revision and cache handling.
  Document transaction boundaries and the limits of cancellation/rollback for
  trusted arbitrary scripts, particularly external side effects and uncooperative
  code; do not promise automatic reversal or safe preemption that cannot be ensured.
- Preserve existing headless capabilities through actual Ghidra script providers,
  including Java and Jython, with getScriptArgs, properties/prompt inputs, nested
  scripts, search paths, explicit program/address/selection, per-job monitors, and
  output/error streams. CPython/PyGhidra is not a drop-in Jython replacement.
  Provide a compatibility implementation for HeadlessScript lifecycle/state where
  needed; fresh GhidraState and a headless flag alone are not equivalent. Include
  loader/analyzer options and import/export capabilities. Inventory all supported
  script providers and headless operations in a tested capability matrix. GUI-only
  plugins, interactive widgets, and debugger workflows must not be silently claimed
  as supported by a static headless service. Surface any actual capability gap
  to the user; do not mark complete by quietly excluding required headless behavior.
- Cooperative cancellation targets the specified job only. Recover a failed native
  decompiler without terminating other jobs or unrelated processes. An uncooperative
  script or engine failure can require the supervisor to restart the engine and
  interrupt other work. Report that distinction honestly; never use unsafe Java
  thread termination to claim isolated cancellation. Define script state cleanup,
  disconnect handling, shutdown, recovery, and uncertain outcomes explicitly.
- Freeze results into immutable output records before releasing read leases; do
  not cache live Program/Function/HighFunction objects. Key cached results by target
  identity, restart-unique engine/program generation, revision, and effective options.
  Reset request options between decompiler leases. Conservatively invalidate after
  writes and reset/recreate interfaces when structural changes require it. Version
  numbers identify states but do not preserve historical snapshots.
- Specify save semantics and test durability. Distinguish transaction completion
  from saving the program to disk, and report whether a successful edit is durable.
  Preserve the expected save-after-success behavior of invocation-style workflows
  through an explicit policy; never silently acknowledge unsaved work as persisted.
- Emit structured results and local evidence records with target binary hash,
  Ghidra version, program identity and revision, arguments/options, job ID, status,
  and output or error. Measure queue time separately from compute time.
- Secure the localhost service against unintended cross-origin/browser access;
  avoid unauthenticated arbitrary script execution. Keep authentication/configuration
  project-local and avoid unnecessary infrastructure.
- Package a single documented start/status/stop workflow and client connection
  configuration. Multiple agent connections must share the running service rather
  than spawn a JVM each. Include project-local installation/configuration examples,
  health reporting, restart/save behavior, and clean ownership-aware shutdown.

## Internal implementation order (all steps required before delivery)

1. Read upstream README, pom.xml, Java plugin, Python bridge, and official APIs.
   Write a concise architecture note and reproducible local build instructions.
2. Build a small synthetic binary fixture from checked-in source. Import/analyze
   it once into a single disposable local project. Preserve any original database
   outside this checkout by never opening it.
3. Prove overlapping real decompilation jobs through separate decompiler instances
   using the same Program. Compare outputs to a serial baseline. Do not substitute
   concurrent HTTP acceptance with serialized backend work and call it parallel.
4. Add the persistent host, pool, session/job API, MCP bridge, bounded resource
   policies, cancellation, full editing/script/reanalysis capabilities, persistence,
   and local packaging. The concurrency proof is an internal checkpoint, not delivery.
5. Run correctness and performance validation; document actual limitations and
   prepare a staged upstream contribution plan without posting anything.

## Acceptance and measurements

- Two or more MCP clients complete independent overlapping analysis jobs correctly
  against one loaded Program. Record evidence of actual backend overlap.
- A sequential and concurrent run of the same functions produces matching results
  under identical revision/options, or explains and investigates any discrepancy.
- Measure first-request cost and warm throughput/latency for worker counts 1, 2,
  and 4 when feasible. Record machine/toolchain, fixture, request mix, repeat count,
  queue delay, end-to-end latency, and all owned JVM/native process memory. Separate
  result-cache hits from real decompilation and avoid claiming unmeasured speedups.
- Measure storage and memory as session count grows while worker count stays fixed.
  Demonstrate no per-session project or Program/JVM duplication, and that closed
  sessions release metadata/results according to bounded retention policies.
- Test queue saturation, cancellation of queued/running jobs, timeout, worker
  failure/recovery, resource cleanup, and clean shutdown. One cancelled request
  must not cancel another client's work under the cooperative/worker-isolated contract.
  Separately test uncooperative scripts and engine crash/restart, interruption
  reporting, recovery from the last durable state, and suppression of unsafe replay.
- Test conflicting revisions, read/write coordination,
  rollback, subsequent decompilation/cache freshness, and writer progress under load.
- Validate every supported tool category, script output/error/cancellation behavior,
  reanalysis completion, datatype effects on decompilation, and save/reopen persistence.
  Test multiple simultaneous MCP clients using the one packaged service and explicit
  program routing. Document any unavoidable limits rather than omitting operations.
- Compare ordinary analyzeHeadless invocation against the service on identical
  fixtures using the same Ghidra version/options first. Separately characterize
  differences from the older toolchain; do not attribute version changes to the
  scheduler. Cover Java/Jython script context, headless lifecycle, nested scripts,
  analysis policy, imports/exports, failure effects, and save behavior. Keep all
  fixtures and test distributions isolated from the existing setup.
- Add a larger generated fixture and mixed query/write workloads to the benchmark.
  Bound total analyzer/decompiler CPU and memory budgets, benchmark batching and
  identical-read coalescing, and size the worker pool from measurements. Do not call
  a tiny-fixture result proof of optimal performance on a large game database.
- Provide build/run/test commands, an example with two clients, a benchmark report,
  known limitations, and a proposed sequence of focused upstream changes.
- No automatic integration with the user's current tools; completion is the full
  working isolated product described above. Leave changes uncommitted for review.

## Starting references

- https://github.com/LaurieWired/GhidraMCP
- https://ghidra.re/ghidra_docs/api/ghidra/app/decompiler/DecompInterface.html
- https://ghidra.re/ghidra_docs/api/ghidra/app/decompiler/parallel/ParallelDecompiler.html
- https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/java/ghidra/app/decompiler/parallel/DecompilerCallback.java
- https://github.com/NationalSecurityAgency/ghidra/discussions/7523

Verify these against the pinned version. Ghidra already pools decompilers against
one Program; internal database locks can still limit scaling. A Ghidra core fork
is not the planned implementation approach. Profile before proposing changes to
core locking, and explain any evidence-backed architectural blocker to the user.
