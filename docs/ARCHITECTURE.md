# Shared program service

The public transport is authenticated MCP Streamable HTTP on an explicitly configured
loopback port. A Python supervisor owns the listener, bounded SQLite job journal,
session admission, FIFO read/write scheduling, and one engine process group. Clients
never launch Ghidra. Java owns a single writable project and a bounded map of programs.
The supervisor communicates with its child over an authenticated private loopback
connection. This connection is an implementation detail, not an agent API.

The upstream plugin depends on GUI selection, serial HTTP dispatch, and per-request
decompilers. Its useful operations are extracted into explicit program queries
and atomic edit batches; its GUI server is not part of the service package. Upstream
source and license remain available for provenance. The Maven build depends on
manually copied system jars; the service build uses javac against the verified local
Ghidra distribution instead, without modifying a shared extension installation.

Reads freeze JSON before releasing the reservation. A queued writer stops admission
of later reads and runs after earlier reads drain. Revision checks occur inside the
write reservation. Atomic edit batches commit one transaction, or roll back all their
changes. Analysis and scripts are exclusive, may use multiple transactions, and have
weaker rollback guarantees. Native interfaces are leased exclusively, reused across
reads, and disposed after structural edits. Cache keys include generation, program,
revision and effective request arguments. Versions are conflict tokens, not snapshots.

Ghidra 12.1.3 is pinned by the official release SHA-256. The pinned source confirms
DecompilerCallback pools interfaces against the same Program, HeadlessAnalyzer is a
singleton, and AutoAnalysisManager executes scripts synchronously in headless mode.
Consequently one controlled engine lane runs all analysis, scripts and lifecycle jobs.
No Ghidra internal database lock is held while awaiting a separate analysis thread.

The supervisor retains interrupted jobs without replaying them. Recovery kills only
its own process group, waits for owner exit, and reopens durable program state with a
new generation. Cooperative cancellation sets only the job monitor; an unresponsive
engine needs engine-wide recovery and can interrupt other jobs. Arbitrary trusted
scripts are not sandboxed and must join their background work before returning.

Primary source audit:

- [Pinned release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.3_build)
- [DecompilerCallback](https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.3_build/Ghidra/Features/Decompiler/src/main/java/ghidra/app/decompiler/parallel/DecompilerCallback.java)
- [AutoAnalysisManager](https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.3_build/Ghidra/Features/Base/src/main/java/ghidra/app/plugin/core/analysis/AutoAnalysisManager.java)
- [HeadlessAnalyzer](https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.3_build/Ghidra/Features/Base/src/main/java/ghidra/app/util/headless/HeadlessAnalyzer.java)
- [GhidraScript](https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.3_build/Ghidra/Features/Base/src/main/java/ghidra/app/script/GhidraScript.java)
