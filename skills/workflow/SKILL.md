---
name: workflow
description: Use the shared Ghidra MCP for reverse engineering, decompilation, disassembly, queries, coordinated edits, scripts, reanalysis, and retained evidence. Multiple agents share one owner and explicit program state.
---

# Shared Ghidra workflow

Use the plugin's `ghidra` MCP. Host prefixes may qualify its tool names.
Never invoke a GUI bridge or analyzeHeadless per request, or create a Program,
project or JVM copy for another session.

1. Read the consumer repository's target map and investigation conventions.
2. Call `service_health`, then `session_open`, then submit `programs`. Confirm
   the project, explicit Program ID and binary hash. Never assume GUI selection,
   a default executable, or matching addresses across builds.
3. Submit `job_submit(session, operation, arguments, timeout_seconds)`. Poll
   `job_result(session, job)` until terminal. Accepted is not completed.
4. Retain the completed envelope in the investigation's evidence location before
   `session_close`: binary SHA-256, Ghidra version, Program/full version, job ID,
   arguments/options, status, effect, durable state and output/error.
5. Close your session. Do not stop the service when an individual job ends.

Read [the API](../../docs/API.md) for exact arguments and
[the capability matrix](../../docs/CAPABILITIES.md) for tested providers/limits.

## Parallelism and shared edits

Four supported reads total may overlap on one or multiple loaded Programs.
Additional sessions queue fairly. There is one loaded instance per target.
Sessions are not database branches; applied changes are shared. Queries and
native decompilation overlap. Edits, imports/exports, scripts, auto-analysis
and lifecycle jobs reserve the service exclusively.

Every mutation supplies the latest full `expected_version`. On `stale_revision`,
read again and reconsider; never blindly refresh and retry the same edit.
Atomic edit batches roll back on failure/cancellation and save by default.
Inspect `durable`; transaction success alone does not prove a disk save.
Versions are restart-unique state labels, not historical snapshots.

## Scripts, evidence and cancellation

Java and Jython use actual Ghidra providers; host Python is not Jython. Use
explicit target/address/selection, args and script paths. Retain source hashes.
Files must be staged inside the private installation. Its `tools/recorded_job.py`
accepts `--workspace`, `--script`, `--script-dir`, repeated `--script-arg`,
`--program`, `--analyze`, `--timeout`, `--evidence` and `--log`. It snapshots
only script/property files from an explicit workspace subdirectory and records
accepted and terminal jobs. Consumer wrappers may supply repository defaults.

Unrestricted scripts can mutate either loaded Program or external state. They
run exclusively, advance all loaded revisions, and cannot promise full rollback.
Scripts must not leave background mutation threads or launch another owner.
Cooperative cancellation targets a job. Uncooperative code can require
engine-wide recovery, interrupt others, and leave uncertain effects. Never kill
Java by name or promise isolated forced script termination. Recovery reopens
durable targets and does not replay uncertain writes.

## Ownership

The private Windows installation defaults to `~/ghidra-shared`; an explicitly
configured `GHIDRA_SHARED_HOME` may override it. Plugin caches contain software
and instructions, never live credentials or databases. Use [setup](../setup/SKILL.md)
for lifecycle management. Coordinate stop/restart/close across all clients.
Never open the service's writable project in a GUI while it is owned. Never run
destructive fixture/reset validation against a consumer database.

This plugin owns general tool rules. Consumer repositories own binary identity,
target mapping, investigation scripts, reports and evidence destinations.
