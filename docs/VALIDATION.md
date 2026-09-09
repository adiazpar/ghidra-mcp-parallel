# Measured validation

Measurements were made on 2026-09-08 on Windows 11 build 26200, an AMD64 Family 26
Model 68 processor with 16 logical CPUs, and 33,408,585,728 bytes of RAM. Runtime:
Ghidra 12.1.3, Temurin 21.0.11+10, CPython 3.12.9. Ghidra release and dependency pins
are in `toolchain.json` and `requirements.lock`. The upstream plugin also compiled
against the local pinned distribution during the source audit.

Only the checked-in C fixture and generated C source were used. The larger fixture
has 256 exported functions, each with 48 generated conditional arithmetic steps,
built with MSVC 14.44.35207 `/O1 /GS- /Zl /nodefaultlib`. Its analyzed input SHA-256 is
`ffb81e43165eb9bc5dac559b4355a439e86754275400ba9bbaee66e89fc57f95`.
It is intentionally larger than the small fixture, but is still a synthetic benchmark,
not a proxy for a large game database. Rebuilding PE files can change their timestamps
and input hashes; each evidence record contains the actual imported binary hash.

## Parallel reads

Eight lightweight client sessions requested the same 24 larger-fixture functions
for three repeats at each worker count. Output-cache and identical-read coalescing
were disabled for these measurements. Requests were submitted individually over MCP.
Every concurrent output matched its same-revision/options serial baseline. Native
start/end intervals overlap across distinct worker IDs on the same Program instance;
this is backend overlap, not merely concurrent HTTP acceptance.

| Workers | Throughput (72 jobs / total wall time) | Median latency* | Median queue delay* | First request after engine start | Owned process RSS snapshot |
|---:|---:|---:|---:|---:|---:|
| 1 | 18.6 jobs/s | 359.5 ms | 314.7 ms | 453.2 ms | 407.0 MiB |
| 2 | 30.7 jobs/s | 181.2 ms | 121.7 ms | 455.9 ms | 459.2 MiB |
| 4 | 46.9 jobs/s | 73.5 ms | 9.1 ms | 473.8 ms | 498.7 MiB |

*Median of the three repeat medians. Individual repeat summaries are retained in
local evidence. The first-request measurement starts after the engine/project open
is ready and includes first decompiler setup. It does not include service startup or
import/analysis. RSS includes the owner JVM and all observed owned native/console
descendants at the end of the last repeat; it is not a process-peak estimate.

Four workers were fastest in this measured workload, at about 2.5 times one-worker
throughput with roughly 92 MiB additional observed RSS. The packaged default is four,
bounded to four read workers and four analyzer CPUs, with a 4 GiB JVM heap and a
6 GiB Windows process-group memory budget. More sessions do not create more workers.
Results do not establish linear scaling or an optimal setting for every database.

One 24-function sequential batch took 0.995–1.039 seconds across configurations.
Batching reduces protocol calls but holds one reservation and does not spread its
functions over workers. For parallel throughput, submit independent jobs. A separate
eight-identical-request test coalesced zero, four and six jobs at worker counts one,
two and four. Cache-hit checks are separately labeled; neither cache nor coalescing
is counted as native computation speedup in the table.

## Shared writes and session growth

A mixed workload repeated an ordered group of two reads, one saved edit and a later
decompilation 12 times. All 48 jobs succeeded. Every writer started after the earlier
reads finished, and every later read started after its writer finished. Total wall
time was 7.996 seconds (6.00 jobs/s), median job latency 285.3 ms, p95 518.8 ms, and
median queue delay 118.6 ms. Conservative global decompiler invalidation after writes
has a measurable cost; these numbers are separate from the read-only benchmark.

At fixed worker count four, adding 0, 8, 32, 64 and 100 sessions left project storage
unchanged at 24,332,180 bytes. There was still one owner JVM and the same loaded target
set. Supervisor RSS varied from 64.1 to 64.8 MiB; engine/descendant RSS did not grow
with session count in this run. After closing the added sessions the session count
returned to zero. These snapshots support the absence of per-session Program/project/
JVM duplication; they are not a precise per-session allocation measurement.

## Ordinary headless comparison

Identical larger-fixture input and default analysis options were imported into separate
disposable projects. Each ordinary invocation decompiled the same eight functions.
The service used its already imported target and equivalent decompiler options.

| Ordinary invocation | Full JVM startup, import, analysis, script and save wall time | Per-function native compute range | Output matching service |
|---|---:|---:|---:|
| Ghidra 12.1.3 | 19.54 s | 36.1–59.5 ms | 8 / 8 |
| Ghidra 11.3.2 | 27.39 s | 111.0–134.1 ms | 8 / 8 |

These are single ordinary invocations, not statistically strong version benchmarks.
Their wall time includes different work than the warm-service latency table, so no
speedup ratio is claimed between those columns. The older-version difference is
recorded separately and is not attributed to the service scheduler. Peak memory
sampling is stored as the sum of individual owned-process peak RSS values, which
need not occur simultaneously.

Additional ordinary-invocation tests on both versions matched service Java/Jython
context, arguments, properties, nested scripts and output/error probes. They checked
analysis disable policy, import/process lifecycle and saved partial effects after a
script failure. The deliberate service failure-save policy is described in the
[capability matrix](CAPABILITIES.md).

## Correctness and failure checks

The documented `tools/validate.ps1` workflow completed with **22 passed** in 53.05
seconds, including fresh fixture compilation/import. An additional direct check
verified stdio initialization and structured MCP results without changing the engine
PID. Pytest scratch files are confined to `.local/pytest-tmp`.

The live suite covers two official SDK clients; all query categories; atomic rollback;
stale revisions; datatype/prototype/local-variable effects; saved and volatile edits;
save/close/reopen; source and compiled Java; Jython output/errors/cancellation;
headless continuation and import-directory behavior; function creation; analysis;
export; queue saturation; writer progress; cache/batch behavior; session ownership;
authentication/Origin/Host checks; isolated running-read cancellation; native-worker
crash recovery; JVM exit; uncooperative-script recovery without unsafe replay;
analysis-stage timeout propagation to post-scripts; and cancellation rollback of a
running atomic edit batch.
The supervisor unit test checks bounded journal eviction and idle-session output
release. XML test results are written to `.local/validation/junit.xml`.

Recovery testing verifies a new engine generation, termination of the old owner,
reopening of the last durable state, loss of deliberately volatile changes, and
retention of the interrupted job's `outcome_unknown` status. Cooperative cancellation
does not claim rollback of arbitrary scripts. Trusted scripts retain the shared JVM
failure boundary described in [the API contract](API.md).

## Reproduce and inspect

Run `tools/install.ps1 -Comparison` while stopped to install the isolated comparison
distribution, then start the service and run `tools/validate.ps1 -Benchmarks`.
The comparison archive SHA-256 is a recorded hash of the official downloaded asset;
unlike the 12.1.3 asset, the older GitHub release API did not provide a digest.

Detailed job evidence: `.local/validation/*.json` and `.local/runtime/jobs.sqlite`.
Benchmarks: `.local/measurements/workers-{1,2,4}.json`, `sessions.json`, `mixed.json`,
and `baseline-*.json`. Context comparisons: `.local/compatibility/report.json`.
These files remain local and are excluded from the package because operational
evidence can contain paths and arguments. A portable numeric summary is checked in
as [measurements.json](measurements.json). No existing installation, endpoint,
global configuration or private database was used or changed.
