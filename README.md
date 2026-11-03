# fab-mcp

> **Status:** personal project. I use it on my own NixOS desktop to give AI coding agents control of FreeCAD and Blender. The Bambu Lab printer server is templated but turned off until printer secrets are added, so the print step is not exercised yet.

Wire **FreeCAD**, **Blender**, and **Bambu Lab** (slicing + printing) into your AI
agent fleet -- **Claude Code, Codex, OpenCode, Gemini** -- over the Model Context
Protocol, from one canonical config.

This is a **documentation + scripts** project. No application code: it manages MCP
server definitions and generates the right config for each agent.

## Quick start

```bash
git clone <this-repo> ~/Projects/fab-mcp && cd ~/Projects/fab-mcp
bash scripts/setup.sh            # check deps, stage addons, wire all 4 agents
# (optional) preview wiring without touching anything:
bash scripts/setup.sh --dry-run
```

That wires **FreeCAD** and **Blender** into all four agents. **Bambu** stays
disabled until you add printer secrets:

```bash
cp config/.env.example config/.env   # then fill in PRINTER_HOST / SERIAL / TOKEN / MODEL
# set "bambu".enabled = true in config/servers.json
python3 scripts/wire-agents.py
```

## How it works

`config/servers.json` is the single source of truth. `scripts/wire-agents.py`
reads it and writes each agent's native format:

| Agent | File | Key |
|-------|------|-----|
| Claude Code | `~/.claude.json` | `mcpServers` |
| Codex | `~/.codex/config.toml` | managed `[mcp_servers.*]` block |
| OpenCode | `~/.config/opencode/opencode.jsonc` | `mcp` |
| Gemini | `~/.gemini/settings.json` | `mcpServers` |

Re-running is safe -- only fab-mcp-managed entries are touched, a file whose
content would not change is left alone, and before any change the previous
version is copied to `*.fab-mcp.bak`.

Tests (stdlib only, run against a throwaway `HOME`):

```bash
python3 -m unittest discover -s tests -v
```

## Runtime prerequisites

The MCP servers connect to the running GUI apps:

- **FreeCAD** -> `MCP Addon` workbench -> `Start RPC Server`
- **Blender** -> enable `Blender MCP` addon -> N-panel -> `Connect to Claude`
- **Bambu** -> printer in LAN-Only + Developer Mode, `config/.env` filled

> Bambu warning: the wrong `BAMBU_MODEL` can crash the bed into the nozzle. Verify.

## What is in this repository

The scripts here (about 500 lines of Python and Bash) are the registry, the generator and the setup helpers. The MCP servers themselves are third-party projects, fetched at install time by `scripts/install-addons.sh` into `addons/vendor/`, which is gitignored and not redistributed here:

- [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) (MIT)
- [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp)
- [rowbotik/bambu-printer-mcp](https://github.com/rowbotik/bambu-printer-mcp) (GPL-2.0, a fork of DMontgomery40/bambu-printer-mcp), run through `npx` as `@rowbotik/bambu-printer-mcp`

Design choices worth knowing:

- **One registry, four formats.** Each agent stores MCP servers differently (JSON, TOML, JSONC). The generator owns only the entries it created and leaves everything else in those files alone.
- **Idempotent.** A second run leaves every file byte-for-byte identical, with the same modification time, because unchanged files are not rewritten. The test suite checks this.
- **Atomic writes with backups.** Each write goes to a temp file in the same directory, is fsynced, then renamed over the target, so a crash or another program writing the same file (Claude Code rewrites `~/.claude.json` often) never leaves a half-written config. Before each change, the previous version is copied to `*.fab-mcp.bak`, which keeps one step of history. Symlinked configs are written through, not replaced.
- **Fail closed on secrets.** A server that needs values from `config/.env` is skipped if they are missing, rather than written with blanks.
- **Secrets are copied, so files are private.** MCP clients read server environment from their own config, so enabling Bambu puts the printer access code into all four agent configs. Because of that, every file the generator writes, and every backup, is set to mode `0600`. The access code only controls a printer on your LAN, but treat those files as secrets all the same.

Known limits:

- **JSONC comments are dropped.** OpenCode's `opencode.jsonc` is parsed (comments and trailing commas are handled) and written back as plain JSON. If the file had comments, the script says so, and the commented version is in the backup.
- **The registry owns its names.** Every server name in `config/servers.json` is managed, even when disabled. A hand-made entry with the same name (say, your own `blender`) is replaced or removed. Use a different name for servers you manage by hand.

## Platform support

Tested targets: **NixOS** and **Ubuntu 22.04 / 24.04**.

- `scripts/_detect.sh` auto-resolves OS family and the FreeCAD/Blender/BambuStudio
  paths, so nothing is hardcoded to one distro. Check what it found:
  `bash scripts/detect-paths.sh`.
- **NixOS**: install tools via `configuration.nix`; this repo never touches system packages.
- **Ubuntu/Debian**: `bash scripts/bootstrap-ubuntu.sh` installs freecad, blender, node and
  uv (BambuStudio is a separate AppImage download).
- Snap/Flatpak FreeCAD or Blender use different addon dirs — override with
  `FREECAD_MOD_DIR` / `BLENDER_ADDON_DIR` / `SLICER_PATH`.

The four agent config files live at the same paths on both distros, so the wiring step
is identical everywhere.

> chezmoi: the agent configs are runtime state and aren't chezmoi-managed by default. If you
> manage one with chezmoi, wire the live file then `chezmoi add` it — don't have both own
> the same lines.

## Licence

MIT, see `LICENSE`. The third-party MCP servers keep their own licences.
