#!/usr/bin/env bash
# fab-mcp :: install-addons -- stage the FreeCAD and Blender in-app addons that
# the MCP servers talk to. Works on NixOS and Ubuntu 22/24 (paths auto-detected).
#
# The uvx servers (freecad-mcp / blender-mcp) connect to a socket exposed by
# these addons running inside the GUI app.
#
# Override detection with env vars if needed:
#   FREECAD_MOD_DIR=...  BLENDER_ADDON_DIR=...
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
. "$HERE/_detect.sh"

VENDOR="$ROOT/addons/vendor"
mkdir -p "$VENDOR"

OS="$(fab_detect_os)"
FREECAD_MOD_DIR="$(fab_freecad_mod_dir)"
BLENDER_ADDON_DIR="$(fab_blender_addon_dir)"

echo "fab-mcp :: install-addons   (os: $OS)"
echo "  FreeCAD Mod dir : $FREECAD_MOD_DIR"
echo "  Blender addons  : $BLENDER_ADDON_DIR"
case "$OS" in
  debian) echo "  note: if FreeCAD/Blender are Snap or Flatpak builds, addon dirs differ -- see Install-Guide." ;;
esac
echo

# ---- FreeCAD: clone repo, copy the FreeCADMCP workbench addon ----
echo "==> FreeCAD MCP addon (neka-nat/freecad-mcp)"
if command -v freecad >/dev/null 2>&1; then
  if [ ! -d "$VENDOR/freecad-mcp/.git" ]; then
    git clone --depth 1 https://github.com/neka-nat/freecad-mcp.git "$VENDOR/freecad-mcp" \
      || echo "  ! clone failed (offline?). Skipping FreeCAD addon."
  else
    git -C "$VENDOR/freecad-mcp" pull --ff-only -q 2>/dev/null || true
  fi
  if [ -d "$VENDOR/freecad-mcp/addon/FreeCADMCP" ]; then
    mkdir -p "$FREECAD_MOD_DIR"
    cp -r "$VENDOR/freecad-mcp/addon/FreeCADMCP" "$FREECAD_MOD_DIR/"
    echo "  installed -> $FREECAD_MOD_DIR/FreeCADMCP"
    echo "  next: open FreeCAD -> 'MCP Addon' workbench -> 'Start RPC Server'"
  else
    echo "  ! addon source not found; FreeCAD addon not installed."
  fi
else
  echo "  ! freecad not on PATH; skipping (install it first)."
fi
echo

# ---- Blender: fetch addon.py, drop into the addons dir ----
echo "==> Blender MCP addon (ahujasid/blender-mcp)"
if command -v blender >/dev/null 2>&1; then
  mkdir -p "$BLENDER_ADDON_DIR"
  ADDON_URL="https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py"
  if curl -fsSL "$ADDON_URL" -o "$VENDOR/blender_mcp_addon.py"; then
    cp "$VENDOR/blender_mcp_addon.py" "$BLENDER_ADDON_DIR/blender_mcp_addon.py"
    echo "  installed -> $BLENDER_ADDON_DIR/blender_mcp_addon.py"
    echo "  next: Blender -> Edit > Preferences > Add-ons -> enable 'Interface: Blender MCP'"
    echo "        then N-panel -> BlenderMCP -> 'Connect to Claude'"
  else
    echo "  ! download failed (offline?). Blender addon not installed."
  fi
else
  echo "  ! blender not on PATH; skipping (install it first)."
fi
echo

echo "Addon staging complete. Run scripts/wire-agents.py to wire the MCP servers."
