# Proposed upstream contribution sequence

The user authorized committing and pushing the complete product to their fork.
No upstream pull request or maintainer contact has been authorized or performed.
These are review boundaries for the complete local product, not partial delivery
milestones offered to users.

1. Extract explicit-program query and edit operations from GUI selection. Preserve
   copyright/license notices and document the incompatible GUI-current-state calls.
2. Introduce persistent decompiler leases, frozen results, option reset, cache bounds,
   cancellation and the shared-program overlap/equality tests.
3. Add the owner core, program/project lifecycle, revision checks, atomic edits,
   supported analysis lane and explicit commit/save semantics.
4. Review the version-pinned HeadlessScript compatibility adapter separately, along
   with Java/Jython/nested/prompt/continuation fixtures and stock-headless comparisons.
   A supported upstream lifecycle attachment API would remove the reflection shim.
5. Add the external supervisor, authenticated MCP transport, bounded durable jobs,
   Windows Job Object ownership and engine-failure recovery tests.
6. Add isolated packaging, two-client examples, benchmark harnesses and measured
   reports. Retain clear limits: synthetic fixtures, shared revisions and the shared
   failure boundary of trusted arbitrary scripts.

The current measurements demonstrate useful scaling without modifying Ghidra's
database locking or core. They do not justify proposing a Ghidra core fork. Before
any core optimization proposal, profile representative authorized larger databases
and distinguish native analysis time, database contention, queue delay, transport
overhead and cache effects.
