# One product, one private installation

`adiazpar/ghidra-mcp-parallel` is both the service source repository and the
versioned agent plugin. No separate plugin repository is required. The two
manifests follow the same layout as re-discipline: `.claude-plugin/`,
`.codex-plugin/`, one `.mcp.json`, shared `skills/`, scripts and documentation.

| Location | Responsibility |
|---|---|
| Product repository | Source, manifests, general operating rules, tests and packages |
| `~/ghidra-shared` | Private Ghidra installation, Python environment, configuration, database and runtime state; not a Git repo |
| Consumer repository | Target IDs/hashes, analysis scripts, findings and retained evidence |
| Agent plugin caches | Installed version of this product's integration and skills; no private databases |

## Install once on Windows

Requires uv, a Python bootstrap and JDK 21.0.11. From a checkout or installed
plugin directory, run:

```powershell
powershell -NoProfile -File scripts/deploy.ps1
powershell -NoProfile -File scripts/service.ps1 start
powershell -NoProfile -File scripts/service.ps1 status
```

The default private installation is `~/ghidra-shared`, port 18766. `-Root`
selects another directory; clients can select it with `GHIDRA_SHARED_HOME` in
their launch environment. No global environment changes are needed for the
default. The service installs its own Python 3.12.9 environment and verified
Ghidra 12.1.3 distribution, bundled Jython provider and compiled service engine.
It never changes a consumer's Python dependencies or another Ghidra installation.

The private directory contains:

```text
ghidra-shared/
  VERSION                  installed product version
  .venv/                   service-owned Python environment
  .local/
    ghidra_12.1.3_PUBLIC/   dedicated Ghidra distribution
    config.json            endpoint, resource limits and private token
    software.json          installed software version/provenance
    runtime/               logs, bounded journal, owner state and caches
  runtime/
    projects/              persistent Ghidra project databases
    inputs/                staged binary inputs
    scripts/               immutable per-job script snapshots
  service/, engine/, tools/, scripts/, skills/, docs/
                            installed software and operating instructions
```

Install the same version for both clients:

```powershell
codex plugin marketplace add adiazpar/ghidra-mcp-parallel
codex plugin add ghidra-mcp-parallel@ghidra-mcp-parallel
claude plugin marketplace add adiazpar/ghidra-mcp-parallel
claude plugin install ghidra-mcp-parallel@ghidra-mcp-parallel --scope user
```

Remove an obsolete *project-level* registration for this Ghidra connection when
adopting the plugin, so it is not registered twice. Preserve unrelated servers.
Start a new agent session or reload its plugins. The plugin starts a lightweight
stdio forwarder per client; the forwarders never launch Ghidra. All clients
reach one authenticated loopback endpoint. There is no GUI prerequisite.

See [official plugin packaging](https://learn.chatgpt.com/docs/build-plugins)
and [plugin MCP configuration](https://code.claude.com/docs/en/plugins-reference#mcp-servers)
for the host integration contracts. Host tool prefixes may differ; the server
and nine service/job tools are the same.

## Use and update

Read [the workflow skill](../skills/workflow/SKILL.md). Consumer repositories
need only a short target map and their own evidence/script conventions. Native
queries and decompilation support four concurrent reads across shared targets.
Scripts/edits/analysis remain coordinated and require explicit target revisions.

PowerShell wrappers can invoke the installed `tools/recorded_job.py` through
the installed `.venv/Scripts/python.exe`. A Java/Jython script executes inside
the same persistent Ghidra owner. It is not tied to an older analyzeHeadless
launcher. The CLI snapshots scripts, records accepted/terminal jobs, saves on
success and supports logs and cooperative service timeouts.

For updates: coordinate clients, save, stop with `scripts/service.ps1 stop`,
update the plugin, run its `scripts/deploy.ps1 -Update`, then restart and verify
targets. The updater replaces software only, preserves configuration and
databases, and refuses to update while the supervisor holds its lock. Plugin
update alone does not silently upgrade or restart the running service.

`VERSION`, both manifests and CHANGELOG use semantic versioning. Increment the
version for distributed changes; keep both clients and the installed service
on that version. Repository marketplace installation tracks published main;
Git tags can additionally pin releases. `tools/package.ps1` builds a single
service/plugin ZIP with checksums, excluding private data and dependencies.

## Validation and boundaries

The source checkout's `tools/install.ps1` and `tools/service.ps1` create a
separate synthetic development installation on port 18765. Run the destructive
fixture suite only there, then stop it. Never run it on a consumer project.
See [validation](VALIDATION.md), [API](API.md) and [capabilities](CAPABILITIES.md).

Private databases do not belong on GitHub or inside plugin caches. Recycle
legacy projects only with explicit authorization and after verifying the new
saved targets. A fresh import does not contain annotations from old projects.
