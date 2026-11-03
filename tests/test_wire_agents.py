"""Tests for scripts/wire-agents.py.

Each test runs the real script as a subprocess against a throwaway HOME, with
its own servers.json and .env, so nothing on the machine is touched.

Run: python3 -m unittest discover -s tests -v
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "wire-agents.py")

REGISTRY = {
    "servers": {
        "freecad": {"enabled": True, "command": "uvx", "args": ["freecad-mcp"], "env": {}},
        "blender": {"enabled": True, "command": "uvx", "args": ["blender-mcp"], "env": {}},
        "bambu": {
            "enabled": True,
            "command": "npx",
            "args": ["-y", "@rowbotik/bambu-printer-mcp"],
            "env_from_dotenv": ["PRINTER_HOST", "BAMBU_TOKEN"],
        },
    }
}

DOTENV = "PRINTER_HOST=10.0.0.5\nBAMBU_TOKEN=secret-access-code\n"

# Pre-existing user configs with content the generator must preserve.
SEED = {
    ".claude.json": json.dumps({"theme": "dark", "mcpServers": {"mine": {"command": "x"}}}, indent=2),
    ".codex/config.toml": 'model = "o4"\n\n[mcp_servers.mine]\ncommand = "x"\n',
    ".config/opencode/opencode.jsonc": (
        "{\n"
        '  "$schema": "https://opencode.ai/config.json", // trailing comment\n'
        "  /* block comment */\n"
        '  "mcp": {"mine": {"type": "local", "command": ["x"]},},\n'
        "}\n"
    ),
    ".gemini/settings.json": json.dumps({"mcpServers": {}}),
}
CONFIGS = list(SEED)


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class WireAgentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        self.servers = os.path.join(self.tmp.name, "servers.json")
        self.dotenv = os.path.join(self.tmp.name, ".env")
        self.write_registry(REGISTRY)
        with open(self.dotenv, "w") as f:
            f.write(DOTENV)
        for rel, text in SEED.items():
            p = self.p(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(text)
            os.chmod(p, 0o644)  # world-readable, like a fresh install

    def tearDown(self):
        self.tmp.cleanup()

    def p(self, rel):
        return os.path.join(self.home, rel)

    def write_registry(self, reg):
        with open(self.servers, "w") as f:
            json.dump(reg, f)

    def run_wire(self, *extra):
        env = dict(os.environ, HOME=self.home,
                   FAB_MCP_SERVERS=self.servers, FAB_MCP_DOTENV=self.dotenv)
        r = subprocess.run([sys.executable, SCRIPT, *extra], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def snapshot(self):
        snap = {}
        for rel in CONFIGS:
            p = self.p(rel)
            st = os.stat(p)
            with open(p) as f:
                snap[rel] = (f.read(), st.st_mtime_ns, st.st_ino)
        return snap

    def read_json(self, rel):
        with open(self.p(rel)) as f:
            return json.load(f)

    # --- the claims on the resume ---

    def test_second_run_changes_nothing(self):
        self.run_wire()
        first = self.snapshot()
        out = self.run_wire()
        self.assertEqual(self.snapshot(), first)  # same bytes, mtime and inode
        self.assertEqual(out.count("unchanged:"), 4)

    def test_wires_all_four_agents(self):
        self.run_wire()
        for rel in (".claude.json", ".gemini/settings.json"):
            servers = self.read_json(rel)["mcpServers"]
            self.assertEqual(servers["freecad"], {"command": "uvx", "args": ["freecad-mcp"]})
            self.assertIn("bambu", servers)
        oc = self.read_json(".config/opencode/opencode.jsonc")["mcp"]
        self.assertEqual(oc["blender"]["command"], ["uvx", "blender-mcp"])
        with open(self.p(".codex/config.toml")) as f:
            toml = f.read()
        self.assertIn("[mcp_servers.freecad]", toml)
        self.assertIn("[mcp_servers.bambu.env]", toml)

    def test_preserves_unmanaged_content(self):
        self.run_wire()
        claude = self.read_json(".claude.json")
        self.assertEqual(claude["theme"], "dark")
        self.assertEqual(claude["mcpServers"]["mine"], {"command": "x"})
        oc = self.read_json(".config/opencode/opencode.jsonc")
        self.assertEqual(oc["$schema"], "https://opencode.ai/config.json")
        self.assertIn("mine", oc["mcp"])
        with open(self.p(".codex/config.toml")) as f:
            toml = f.read()
        self.assertTrue(toml.startswith('model = "o4"\n\n[mcp_servers.mine]'))

    # --- secrets and permissions ---

    def test_files_and_backups_are_private(self):
        self.run_wire()
        for rel in CONFIGS:
            self.assertEqual(mode(self.p(rel)), 0o600, rel)
            self.assertEqual(mode(self.p(rel) + ".fab-mcp.bak"), 0o600, rel)

    def test_unchanged_file_still_gets_tightened(self):
        self.run_wire()
        os.chmod(self.p(".gemini/settings.json"), 0o644)
        self.run_wire()
        self.assertEqual(mode(self.p(".gemini/settings.json")), 0o600)

    def test_missing_secret_skips_server(self):
        with open(self.dotenv, "w") as f:
            f.write("PRINTER_HOST=10.0.0.5\n")
        out = self.run_wire()
        self.assertIn("missing .env keys ['BAMBU_TOKEN']", out)
        self.assertNotIn("bambu", self.read_json(".claude.json")["mcpServers"])

    # --- backups ---

    def test_backup_holds_previous_version_and_is_refreshed(self):
        self.run_wire()
        with open(self.p(".claude.json.fab-mcp.bak")) as f:
            self.assertEqual(f.read(), SEED[".claude.json"])
        with open(self.p(".claude.json")) as f:
            wired = f.read()
        reg = json.loads(json.dumps(REGISTRY))
        reg["servers"]["blender"]["enabled"] = False
        self.write_registry(reg)
        self.run_wire()
        with open(self.p(".claude.json.fab-mcp.bak")) as f:
            self.assertEqual(f.read(), wired)  # refreshed, not the first-run copy
        self.assertNotIn("blender", self.read_json(".claude.json")["mcpServers"])

    # --- edge cases ---

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        self.run_wire("--dry-run")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(os.path.exists(self.p(".claude.json.fab-mcp.bak")))

    def test_creates_missing_files(self):
        os.remove(self.p(".gemini/settings.json"))
        self.run_wire()
        self.assertIn("freecad", self.read_json(".gemini/settings.json")["mcpServers"])
        self.assertFalse(os.path.exists(self.p(".gemini/settings.json.fab-mcp.bak")))

    def test_symlinked_config_is_written_through(self):
        target = os.path.join(self.tmp.name, "dotfiles-gemini.json")
        os.replace(self.p(".gemini/settings.json"), target)
        os.symlink(target, self.p(".gemini/settings.json"))
        self.run_wire()
        self.assertTrue(os.path.islink(self.p(".gemini/settings.json")))
        with open(target) as f:
            self.assertIn("freecad", json.load(f)["mcpServers"])

    def test_no_temp_files_left_behind(self):
        self.run_wire()
        for rel in CONFIGS:
            d = os.path.dirname(self.p(rel))
            self.assertFalse([n for n in os.listdir(d) if n.endswith(".tmp")], d)


if __name__ == "__main__":
    unittest.main()
