# Tested capability matrix

Validated on Windows 11, Ghidra 12.1.3, Temurin JDK 21.0.11+10 and CPython 3.12.9.
Ghidra's bundled Jython extension is installed in the dedicated local distribution.
Ordinary `analyzeHeadless` comparison also used an isolated Ghidra 11.3.2 distribution.
Neither comparison opens an existing user's project.

| Capability | Implementation and validation |
|---|---|
| One shared Program | Native timing intervals overlap on different worker IDs; all return the same Program identity; serial/concurrent C output matches |
| MCP transport | Two independent official MCP SDK clients initialize and run analysis against the one endpoint; optional stdio forwarding uses the same server |
| Query categories | Functions, address lookup, assembly, xrefs, strings, data, symbols, namespaces/classes, imports/exports, segments, types, options and bytes checked live |
| Function/data/variable names | Transactional changes checked through subsequent query/decompiler results |
| Prototypes/local types | User parameter names and types persist; structured datatype fields appear in decompiled C |
| Datatypes | C declaration parsing, storage and application tested; unknown/ambiguous types fail instead of silently substituting a type |
| Function creation | Disassembly and function creation tested on a freshly imported, unanalyzed fixture |
| Conflicting edits | Expected-version conflict rejected; multi-change failure rolls back and returns original decompilation |
| Read/write consistency | Earlier reads finish before the writer starts; later reads start after it finishes and report its new version |
| Java source | Actual JavaScriptProvider/OSGi compilation, GhidraScript and HeadlessScript tested |
| Compiled Java | `.class` loading, arguments and output tested using a repository-local classpath |
| Jython | Actual JythonScript and GhidraJythonInterpreter; arguments, print, error stream, nested Java, exceptions and monitor cancellation tested |
| Untagged `.py` | Defaults to the actual Jython provider through a registered provider preference; explicit `@runtime` metadata remains honored |
| PyGhidra provider | Discovered but unavailable in this Java-owned engine; reported `available:false`. CPython is not substituted for Jython. Explicit requests fail clearly |
| Script context | Explicit currentProgram, currentAddress, currentSelection, args, prompt/property inputs, output and error capture tested |
| Nested script state | Headless storage and nested arguments tested; state is scoped to one job and reset between jobs |
| Headless lifecycle | Process/import mode, analysis enable/disable, pre/post order, continuation, import-directory changes, import discard and authorized process deletion tested |
| Analysis | Full and changed-program analysis, nested analyzeChanges and completion under the exclusive lane tested; analysis option names are discovered from the Program |
| Import/export | PE import, program identity, no-analysis import, loader/language/compiler configuration, and Ghidra packed export use supported APIs; exporter option parsing uses actual exporter descriptors |
| Persistence | Commit versus save reported separately; save/close/open restores edits; crash discards volatile changes and restores durable state |
| Cancellation | Queued and running script/read jobs cancel independently; another session's read completes; timeout is separately reported |
| Native recovery | Killing an owned native worker is followed by successful requests in the same engine generation |
| Engine recovery | System.exit and an uncooperative script exercise the shared failure boundary; uncertain effects recorded, old owner exits before reopen, no replay |
| Bounds | Queue saturation, writer progress, per-session authorization, result retention, idle expiry and session release tested; storage unchanged through 100 additional sessions |
| Local security | Missing token, browser Origin and unexpected Host rejected; path traversal and filesystem links are contained within the checkout |
| GUI/debugger workflows | Outside the headless static-analysis product; no GUI owner or interactive widget is claimed |

The suite exercises the listed categories; it does not claim every processor, loader,
exporter option, analyzer or arbitrary third-party script is exhaustively tested.
Native Ghidra exporter/provider inventories are discoverable through `capabilities`.
Unsupported runtime requests are explicit errors, not silently translated scripts.

## Compatibility boundaries

The script lane calls the real Ghidra script implementations. Ghidra exposes script
providers publicly, but HeadlessScript attachment and HeadlessAnalyzer project,
continuation/analysis state do not have public setters. `ScriptLane.java` therefore
contains a small adapter pinned to 12.1.3 that accesses those lifecycle hooks. It does
not fork Ghidra or patch the distribution's classes. Upgrading the pin requires
rerunning the capability suite; the adapter fails if the expected hooks disappear.

Jython's normal headless path writes `print` to process stdout and runs a helper
thread that can swallow errors. Supplying a fresh actual Ghidra interpreter through
the script state's existing-interpreter mechanism makes execution synchronous on
the controlled lane, captures output, and propagates failures. Cooperative scripts
must check their provided monitor. An endless Python loop without monitor checks,
blocking native call, or uncooperative Java script can need engine-wide recovery.

The service and ordinary headless invocation produce matching Java/Jython context
probe results on both tested Ghidra versions. One deliberate persistence difference
is tested: ordinary headless can save partial modifications after a failing script;
the service reports `partially_applied` and leaves them volatile unless explicitly
saved. Successful service script jobs save by default. A failure does not mean that
external side effects or script-managed transactions were rolled back.

Generic scripts reserve the entire engine. They must finish their own threads before
returning and preserve service ownership. Ghidra cannot guarantee isolation from
arbitrary trusted code that changes JVM-global state, opens additional owners, exits,
or performs external I/O. Such code has a shared failure boundary. The service never
uses unsafe Java thread termination or claims private per-session database versions.
