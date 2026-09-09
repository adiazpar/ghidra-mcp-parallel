# Project instructions

This is a standalone GhidraMCP fork for a persistent service supporting parallel
agent analysis against one shared Ghidra Program. Read IMPLEMENTATION_PROMPT.md
before implementation, then read DESIGN_REVIEW.md. The user wants the complete product with measured validation,
not a prototype or a sequence of partial releases.

## Isolation boundary

The user explicitly authorized the consumer migration, versioned plugin
installation, recycling of legacy projects and commit/push to their fork on
2026-09-08. The defaults below prohibit unrequested changes; they do not undo
that authorization. Keep all private consumer data outside this public repository.

- Keep development, configuration, test projects, logs, downloads, and runtime
  state inside this checkout. Use a project-local .venv if Python is needed.
- Do not modify, migrate, retire, or depend on the setup in the sibling
  snaphak-re repository. Do not edit its instructions, Python environment,
  tools/re/run.ps1, MCP configuration, or machine-local paths.
- Do not open, copy, upgrade, repair, or write the existing ghidra_projects_gui
  or ghidra_projects_headless projects. Do not call the existing Ghidra MCP
  endpoint, stop existing Ghidra processes, or delete their locks.
- Do not alter shared Ghidra installations, extension directories, user settings,
  global environment variables, or global agent/MCP configuration. Use a dedicated
  local Ghidra distribution and configure its user/cache/temp directories locally.
- Use synthetic test binaries built from source in this repository. No game
  binaries or private analysis databases in the fork or its public artifacts.
- Bind development services to loopback on an explicitly configured unused port;
  avoid the existing service on 8080. Never kill an unrelated process to free a port.
- Cleanup and cancellation must target only resources owned by this service.
  On Windows, track child processes precisely; do not kill by executable name.

## Product constraints

- One persistent headless service and one agent-facing MCP interface. All clients
  reach the same owner; do not offer competing GUI/headless operational paths.
- Keep a lightweight supervisor outside the sole owning engine JVM. Cooperative
  job cancellation and engine-wide crash recovery are different guarantees.
- Deliver parallel reads, coordinated edits, script execution, reanalysis, lifecycle
  management, evidence, packaging, and validation together. Internal implementation
  steps do not permit stopping at a subset of the agreed product.
- One shared on-disk project and one loaded Program per active target, with one
  owning JVM. No full project, Program clone, or JVM per agent session.
- Sessions are lightweight. Bound decompiler workers, queued jobs, retained results,
  and caches. Share persistent DecompInterface instances through exclusive leases.
- Parallel analysis reads; coordinated writes with a defined consistency contract.
  Do not promise private analysis versions from lightweight session metadata.
- Preserve Java/Jython and headless script lifecycle compatibility explicitly;
  provide a tested capability matrix. Unrestricted scripts cannot be promised
  safe parallel execution, complete rollback, or isolated forced termination.
- Build on supported Ghidra APIs and measure
  bottlenecks before proposing core changes.
- Consult current official documentation/source, pin dependencies, and distinguish
  measured results from expectations. Preserve upstream license notices.

## Collaboration and delivery

- Ask concise clarifying questions when product choices need guidance. Continue
  independent work while waiting. The consolidated surface and complete delivery
  scope are already decided; do not ask the user to choose partial versions again.
- Do not commit, push implementation changes, contact maintainers, open issues or
  PRs, or publish releases unless the user authorizes those actions.
- Do not launch external providers or delegate to subagents without user permission.
- Never use emojis or add tool/provider attribution to commits, PRs, release notes,
  changelogs, or file headers. Keep ordinary upstream copyright/license notices.
- Prefer PowerShell on Windows. Keep machine-specific paths out of portable code.
