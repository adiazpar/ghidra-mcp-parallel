# Shared-program service design review

Status: historical architecture review, incorporated into the implementation.
See README.md, docs/INSTALLATION.md and docs/VALIDATION.md for the delivered
service, versioned plugin packaging and measured behavior.

## Verdict

Keep one project owner and one loaded Program per target, with leased decompilers
and lightweight sessions. This is a credible low-memory architecture. It is not
proof of optimal performance, zero regressions, or safe concurrent arbitrary code.

The product contract is full supported headless analysis, editing, import/export,
and scripting access for every connected agent through one interface. Vetted reads
can overlap; writes, generic scripts, and analysis coordinate. All changes are shared.
GUI-only features and debugger workflows are not implied by headless static analysis.

## High-priority corrections

1. Preserve script compatibility explicitly. The existing workflow executes Jython
   scripts with arguments, script paths, headless context, optional analysis, and
   saved results. Java/Jython providers, nested scripts, properties, output capture,
   and HeadlessScript lifecycle need tests. A generic callback or CPython interpreter
   does not provide this compatibility. Require a capability matrix and report gaps.

2. Preserve the analysis execution contract. HeadlessAnalyzer is explicitly not
   thread safe. AutoAnalysisManager contains synchronous headless assumptions;
   putting a lock around HTTP handlers does not coordinate all program events and
   analyzer activity. Use a controlled exclusive lane and verify analysis completion,
   nested analysis, and lock ordering against the pinned Ghidra release.

3. Separate cancellation from recovery. Cooperative operations and native decompiler
   processes can normally be cancelled individually. Arbitrary trusted scripts can
   hang, spawn threads, change global state, exhaust memory, or exit the shared JVM.
   A lightweight supervisor outside the engine must retain job status and recover
   the sole owner. Recovery can interrupt other work. No per-session project copies
   are needed, but the shared engine has a shared failure boundary.

4. Limit rollback promises to atomic service-owned edits. Scripts can own multiple
   transactions, save state, affect other programs, or perform external side effects.
   Analysis may leave partial results. Report rollback, partial application, unknown
   outcomes, changed revision, and durability accurately. Do not replay uncertain
   writes automatically after recovery.

## Consistency and optimization corrections

- Return immutable records rather than retaining live Ghidra objects in result caches.
- Include engine/program generation, revision, target, and options in cache keys.
  A revision label does not preserve an old database snapshot.
- Reset per-request decompiler options; coordinate invalidation and structural resets.
- Make save-to-disk behavior explicit. Transaction commit alone is not durable save.
- Use bounded worker and analyzer resource budgets, fair admission, batching, and
  identical-read coalescing where measured beneficial. Do not assume adding threads
  improves throughput when database synchronization or memory is the bottleneck.
- Compare same-version batch invocation and persistent operation before comparing
  old/new Ghidra versions. Test a larger generated fixture and mixed workloads, not
  only a tiny example. Preserve the separate existing setup throughout validation.

## Recommended runtime

One MCP endpoint/supervisor manages one owning JVM. Inside the JVM, explicit program
handles route requests into a bounded read/decompiler pool or a controlled exclusive
execution lane. Generic scripts reserve the engine because their effects can be
global. Session metadata does not duplicate Program state. Results and job evidence
are bounded and detached from live database objects. Recovery restarts the owner
behind the same interface and reports interrupted or uncertain jobs honestly.

## Primary sources

- Shared Program with multiple pooled DecompInterface instances:
  https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Decompiler/src/main/java/ghidra/app/decompiler/parallel/DecompilerCallback.java
- Persistent decompiler lifecycle, cancellation, cache flushing, and reset behavior:
  https://ghidra.re/ghidra_docs/api/ghidra/app/decompiler/DecompInterface.html
- HeadlessAnalyzer singleton and explicit non-thread-safe contract:
  https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/java/ghidra/app/util/headless/HeadlessAnalyzer.java
- Analysis thread and completion assumptions:
  https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/java/ghidra/app/plugin/core/analysis/AutoAnalysisManager.java
- Script execution state and script-specific headless lifecycle:
  https://ghidra.re/ghidra_docs/api/ghidra/app/script/GhidraScript.html
  https://ghidra.re/ghidra_docs/api/ghidra/app/util/headless/HeadlessScript.html
- Program transactions:
  https://ghidra.re/ghidra_docs/api/ghidra/program/model/listing/Program.html

These links describe current upstream behavior. Implementation must verify the
equivalent source in its pinned release rather than assume master is identical.
