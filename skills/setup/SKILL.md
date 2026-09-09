---
name: setup
description: Install, update, start, inspect or stop the dedicated shared Ghidra service, and explain plugin, private runtime and consumer repository responsibilities.
---

# Shared Ghidra setup

Read [installation and architecture](../../docs/INSTALLATION.md). This repository
packages both agent manifests, shared skills, MCP configuration and service source.
One separate private installation owns Ghidra, its Python environment, credentials,
databases, inputs and logs. Never store these in an agent plugin cache.

The private installation contains only runtime software and data. Agent skills,
documentation, Java source and build/deployment tools stay in this plugin. Run
`scripts/deploy.ps1` and `scripts/service.ps1` from the plugin directory. The private
runtime keeps `tools/service.ps1` and `tools/recorded_job.py` for consumer wrappers.

Run the plugin's `scripts/deploy.ps1` for a new Windows installation, default
`~/ghidra-shared`. It requires uv, Python bootstrap and JDK 21.0.11, creates its
own pinned environment and builds the engine. Do not modify another project's
environment. Use `scripts/service.ps1 start|status|stop`; connecting MCP never
starts another engine. Start a stopped service within the user's task authority;
never create alternate owners as a connection fallback.

For updates, coordinate idle clients, save wanted changes, stop the service,
run `scripts/deploy.ps1 -Update`, restart and verify loaded targets. Plugin
updates do not silently replace the engine or mutate a database. Use the same
product version for service and client plugins; VERSION and manifests are checked.
The updater tracks managed runtime files and retires unchanged legacy software;
inspect any reported modified files it preserves. It never prunes private data.

Never run `tools/validate.ps1` or fixture preparation against production data.
Synthetic validation uses the source checkout's separate development installation.
For consumer data, inspect health, list targets and submit recorded read jobs.
Do not recycle old databases without explicit user authorization.
