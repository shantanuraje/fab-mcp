#!/usr/bin/env bash
# fab-mcp :: detect-paths -- print the auto-detected, machine-specific paths.
# Handy for filling config/.env (SLICER_PATH) and sanity-checking a new box.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/_detect.sh"

echo "os               : $(fab_detect_os)"
echo "freecad_mod_dir  : $(fab_freecad_mod_dir)"
echo "blender_addon_dir: $(fab_blender_addon_dir)"
echo "slicer_path      : $(fab_slicer_path || true)"
echo
slicer="$(fab_slicer_path || true)"
if [ -n "$slicer" ]; then
  echo "Suggested .env line:  SLICER_PATH=$slicer"
else
  echo "BambuStudio not found -- install it (AppImage on Ubuntu) then re-run."
fi
