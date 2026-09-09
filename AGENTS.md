# Project instructions

This repository contains the shared Ghidra service and its versioned agent plugin.
Read README.md for the source layout, docs/DEVELOPMENT.md for build and test commands,
and docs/ARCHITECTURE.md and docs/API.md before changing runtime behavior.

## Isolation boundary

Keep private consumer data outside this public repository. Changes to consumer
repositories, installed services or global plugin configuration require user
authorization; ordinary source maintenance stays in this checkout.

- Keep development, configuration, test projects, logs, downloads, and runtime
  state inside this checkout. Use a project-local .venv if Python is needed.
- Do not change consumer repositories or open their databases during development.
- Do not alter shared Ghidra installations, extension directories, user settings,
  global environment variables, or global agent/MCP configuration. Use a dedicated
  local Ghidra distribution and configure its user/cache/temp directories locally.
- Use synthetic test binaries built from source in this repository. No game
  binaries or private analysis databases in the fork or its public artifacts.
- Bind development services to loopback on an explicitly configured unused port;
  use port 18765 for development. Never kill an unrelated process to free a port.
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
  independent work while waiting.
- Do not commit, push implementation changes, contact maintainers, open issues or
  PRs, or publish releases unless the user authorizes those actions.
- Do not launch external providers or delegate to subagents without user permission.
- Never use emojis or add tool/provider attribution to commits, PRs, release notes,
  changelogs, or file headers. Keep ordinary upstream copyright/license notices.
- Prefer PowerShell on Windows. Keep machine-specific paths out of portable code.
