#!/usr/bin/env bash
# fab-mcp :: setup -- one-shot orchestrator. Runs the full pipeline:
#   1. dependency check   2. addon staging   3. agent wiring
#
# Safe to re-run (idempotent). Pass --dry-run to preview agent wiring only.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "######## fab-mcp setup ########"
echo

bash "$HERE/scripts/check-deps.sh" || { echo "Resolve missing deps first."; exit 1; }
echo

if [ "${1:-}" = "--dry-run" ]; then
  python3 "$HERE/scripts/wire-agents.py" --dry-run
  echo "(dry-run: skipped addon install)"
  exit 0
fi

bash "$HERE/scripts/install-addons.sh"
echo
python3 "$HERE/scripts/wire-agents.py"
echo
echo "######## done ########"
echo "FreeCAD + Blender are wired into all four agents."
echo "Bambu stays disabled until you fill config/.env and flip enabled:true in"
echo "config/servers.json, then re-run: python3 scripts/wire-agents.py"
