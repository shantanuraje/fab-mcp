#!/usr/bin/env python3
"""fab-mcp :: wire-agents

Reads config/servers.json (the canonical registry) and writes the equivalent
MCP server config into each AI agent's own config format:

  - Claude Code  -> ~/.claude.json            (top-level "mcpServers", JSON)
  - Codex        -> ~/.codex/config.toml       (managed "[mcp_servers.*]" block, TOML)
  - OpenCode     -> ~/.config/opencode/opencode.jsonc  ("mcp", JSON)
  - Gemini       -> ~/.gemini/settings.json     ("mcpServers", JSON)

Idempotent: re-running overwrites only the fab-mcp-managed server keys and
leaves everything else untouched. A file whose content would not change is not
rewritten at all, so a second run changes nothing on disk.

Safe writes: every write goes to a temp file in the same directory, is fsynced,
and is renamed over the target, so a crash or a concurrent writer never leaves
a half-written config. Before each write that changes a file, the previous
version is copied to <file>.fab-mcp.bak (refreshed on every change).

Permissions: agent configs can carry secrets from config/.env (the Bambu access
code), so every file this script writes, and every backup, is mode 0600.

Usage:
  python3 scripts/wire-agents.py            # wire all enabled servers
  python3 scripts/wire-agents.py --dry-run  # show what would change, write nothing
  python3 scripts/wire-agents.py --agent claude,codex   # only some agents

We don't delete: a disabled server is removed from configs (so toggling
enabled:false cleanly unwires it), but the rest of each config is preserved.

Environment overrides (used by the tests, handy for trying a new registry):
  FAB_MCP_SERVERS  path to servers.json  (default: config/servers.json)
  FAB_MCP_DOTENV   path to the .env file (default: config/.env)
"""
import argparse
import json
import os
import re
import sys
import tempfile

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVERS_JSON = os.environ.get("FAB_MCP_SERVERS") or os.path.join(HERE, "config", "servers.json")
DOTENV = os.environ.get("FAB_MCP_DOTENV") or os.path.join(HERE, "config", ".env")

AGENT_FILES = {
    "claude": os.path.join(HOME, ".claude.json"),
    "codex": os.path.join(HOME, ".codex", "config.toml"),
    "opencode": os.path.join(HOME, ".config", "opencode", "opencode.jsonc"),
    "gemini": os.path.join(HOME, ".gemini", "settings.json"),
}

BLOCK_START = "# >>> fab-mcp managed block (regenerate via wire-agents.py) >>>"
BLOCK_END = "# <<< fab-mcp managed block <<<"

PRIVATE_MODE = 0o600


def log(msg):
    print(f"[fab-mcp] {msg}")


def load_dotenv(path):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


# ---------- JSONC parsing ----------

def strip_jsonc(text):
    """Turn JSONC into plain JSON: drop // and /* */ comments and trailing
    commas, but never touch anything inside a string literal (so URLs like
    "https://..." survive). Returns (json_text, had_comments)."""
    out = []
    i, n = 0, len(text)
    had_comments = False
    while i < n:
        c = text[i]
        if c == '"':
            # copy the whole string literal, honouring backslash escapes
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            had_comments = True
            j = text.find("\n", i)
            i = n if j == -1 else j
        elif text.startswith("/*", i):
            had_comments = True
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
        else:
            out.append(c)
            i += 1
    # second pass: remove trailing commas before } or ], outside strings
    s = "".join(out)
    out = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            out.append(s[i:j + 1])
            i = j + 1
        elif c == ",":
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j < n and s[j] in "}]":
                i += 1  # drop the trailing comma
            else:
                out.append(c)
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out), had_comments


# ---------- registry ----------

def resolve_servers():
    """Return {name: {command, args, env}} for every server that should be wired."""
    with open(SERVERS_JSON) as f:
        reg = json.load(f)["servers"]
    dotenv = load_dotenv(DOTENV)
    out = {}
    for name, spec in reg.items():
        if not spec.get("enabled"):
            continue
        env = dict(spec.get("env", {}))
        missing = []
        for key in spec.get("env_from_dotenv", []):
            if key in dotenv and dotenv[key]:
                env[key] = dotenv[key]
            else:
                missing.append(key)
        if missing:
            log(f"WARNING: '{name}' enabled but missing .env keys {missing} -> skipping")
            continue
        out[name] = {
            "command": spec["command"],
            "args": list(spec.get("args", [])),
            "env": env,
        }
    return reg, out


def managed_names(reg):
    return set(reg.keys())


# ---------- safe file writing ----------

def atomic_write(path, text):
    """Write text to path via temp file + fsync + rename, mode 0600.
    path should already be resolved (no symlink)."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, PRIVATE_MODE)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def commit(path, old, new, dry):
    """Write `new` to `path` if it differs from `old` (None = file absent).
    Backs up the previous version first. Always leaves the file at 0600.
    Returns True if content changed."""
    real = os.path.realpath(path)  # write through symlinks, don't replace them
    if old == new:
        if not dry and os.path.exists(real) and (os.stat(real).st_mode & 0o777) != PRIVATE_MODE:
            os.chmod(real, PRIVATE_MODE)
            log(f"  unchanged, tightened permissions to 0600: {path}")
        else:
            log(f"  unchanged: {path}")
        return False
    if dry:
        return True
    if old is not None:
        bak = real + ".fab-mcp.bak"
        atomic_write(bak, old)
        log(f"  backup -> {bak}")
    atomic_write(real, new)
    return True


def read_or_none(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read()


# ---------- JSON-based agents (claude, gemini, opencode) ----------

def wire_json(path, servers, reg, key, opencode=False, dry=False):
    old = read_or_none(path)
    data = {}
    if old is not None and old.strip():
        raw, had_comments = strip_jsonc(old)
        data = json.loads(raw) if raw.strip() else {}
        if had_comments:
            log(f"  NOTE: {path} has comments; the rewritten file is plain JSON, "
                f"so they will be dropped (the previous version goes to .fab-mcp.bak)")
    section = data.get(key, {})
    # drop any previously-managed keys, then add current ones
    for name in managed_names(reg):
        section.pop(name, None)
    for name, s in servers.items():
        if opencode:
            entry = {"type": "local", "command": [s["command"], *s["args"]], "enabled": True}
            if s["env"]:
                entry["environment"] = s["env"]
        else:
            entry = {"command": s["command"], "args": s["args"]}
            if s["env"]:
                entry["env"] = s["env"]
        section[name] = entry
    data[key] = section
    new = json.dumps(data, indent=2) + "\n"
    if commit(path, old, new, dry):
        verb = "would write" if dry else "wrote"
        log(f"  {verb} {sorted(servers)} -> {path} ['{key}']")


# ---------- TOML agent (codex), managed-block approach ----------

def toml_block(servers):
    lines = [BLOCK_START]
    for name, s in servers.items():
        lines.append(f"[mcp_servers.{name}]")
        lines.append(f"command = {json.dumps(s['command'])}")
        args = ", ".join(json.dumps(a) for a in s["args"])
        lines.append(f"args = [{args}]")
        if s["env"]:
            lines.append(f"[mcp_servers.{name}.env]")
            for k, v in s["env"].items():
                lines.append(f"{k} = {json.dumps(v)}")
        lines.append("")
    lines.append(BLOCK_END)
    return "\n".join(lines) + "\n"


def wire_codex(path, servers, dry=False):
    old = read_or_none(path)
    text = old or ""
    # strip any existing managed block
    pattern = re.compile(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\n?", re.DOTALL)
    text = pattern.sub("", text).rstrip("\n")
    block = toml_block(servers)
    new = (text + "\n\n" + block) if text else block
    if commit(path, old, new, dry):
        verb = "would write" if dry else "wrote"
        log(f"  {verb} {sorted(servers)} -> {path} [managed block]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--agent", default="claude,codex,opencode,gemini",
                    help="comma-separated subset of agents to wire")
    args = ap.parse_args()
    targets = [a.strip() for a in args.agent.split(",") if a.strip()]

    reg, servers = resolve_servers()
    if not servers:
        log("no enabled servers resolved (check servers.json / .env). Nothing to wire.")
    log(f"servers to wire: {sorted(servers) or '(none)'}")

    for agent in targets:
        path = AGENT_FILES.get(agent)
        if not path:
            log(f"unknown agent '{agent}', skipping")
            continue
        log(f"{agent}: {path}")
        if agent == "claude":
            wire_json(path, servers, reg, key="mcpServers", dry=args.dry_run)
        elif agent == "gemini":
            wire_json(path, servers, reg, key="mcpServers", dry=args.dry_run)
        elif agent == "opencode":
            wire_json(path, servers, reg, key="mcp", opencode=True, dry=args.dry_run)
        elif agent == "codex":
            wire_codex(path, servers, dry=args.dry_run)

    log("done." + (" (dry-run, nothing written)" if args.dry_run else ""))
    if not args.dry_run:
        log("Restart any running agent sessions to pick up the new MCP servers.")


if __name__ == "__main__":
    sys.exit(main())
