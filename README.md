# Shared Ghidra service

Version **1.0.2**. One persistent headless Ghidra service, packaged as a plugin
for both Codex and Claude Code. All clients share loaded programs and revisions
through one authenticated MCP endpoint. Reads run concurrently; edits, scripts,
analysis and lifecycle operations are coordinated.

## Install and use

Install the plugin from `adiazpar/ghidra-mcp-parallel`. From its directory:

```powershell
powershell -NoProfile -File scripts/deploy.ps1
powershell -NoProfile -File scripts/service.ps1 start
powershell -NoProfile -File scripts/service.ps1 status
```

The dedicated installation defaults to `~/ghidra-shared`. It owns Ghidra, its
Python environment, private configuration and analyzed databases. Consumer
repositories own their target maps, scripts, findings and evidence. Each client
runs a lightweight forwarding adapter; it does not start another Ghidra engine.
Only runtime software is deployed there. Skills, documentation, Java source and
installation tools remain in this repository and the installed plugin package.

See [installation and updates](docs/INSTALLATION.md) for prerequisites, plugin
registration in both clients, configuration and shutdown. Use the
[workflow skill](skills/workflow/SKILL.md) for analysis and editing.

## Repository layout

| Path | Responsibility |
|---|---|
| `engine/` | Java program owner, decompiler pool, operations and script execution |
| `service/` | Python MCP server, supervisor, scheduling, configuration and client |
| `bridge_mcp_ghidra.py` | Stable stdio entry point forwarding to the running service |
| `scripts/` | Plugin commands for private installation and lifecycle |
| `skills/` | Shared setup and analysis instructions |
| `.codex-plugin/`, `.claude-plugin/`, `.agents/`, `.mcp.json` | Plugin manifests, marketplaces and MCP registration |
| `tools/` | Build, install, validate, package and recorded-job commands |
| `tests/` | Integration and unit tests, synthetic fixtures and benchmarks |
| `examples/` | Client usage examples |
| `docs/` | Maintained installation, development and service reference |

Local dependencies and evidence live in ignored `.local/` and `.venv/` directories.
Development databases live in ignored `runtime/`; build and package outputs go to
`target/` and `dist/`. These directories are not committed. Packages include only
the built service JAR from `target/` and exclude private runtime state.

## Reference and development

- [Development](docs/DEVELOPMENT.md): isolated setup, fixtures, tests and packaging.
- [API](docs/API.md): operations, arguments, revisions, persistence and cancellation.
- [Architecture](docs/ARCHITECTURE.md): ownership, scheduling and recovery.
- [Capabilities](docs/CAPABILITIES.md): supported scripts and headless behavior.
- [Validation](docs/VALIDATION.md): measurements, correctness checks and limitations.
- [Changelog](CHANGELOG.md): version history.

This repository is a fork of [GhidraMCP](https://github.com/LaurieWired/GhidraMCP)
and retains its [Apache 2.0 license](LICENSE). The retired GUI implementation and
its Maven build remain available in Git history.
