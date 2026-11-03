#!/usr/bin/env bash
# fab-mcp :: _detect.sh -- shared, sourceable detection helpers.
# Goal: identical behaviour on NixOS and Ubuntu 22.04/24.04 (and other Linux).
# Nothing here mutates the system; it only inspects and echoes paths.

# --- OS family -----------------------------------------------------------
# echoes: nixos | debian | fedora | arch | unknown
fab_detect_os() {
  if [ -e /etc/NIXOS ] || command -v nixos-rebuild >/dev/null 2>&1; then
    echo nixos; return
  fi
  if [ -r /etc/os-release ]; then
    . /etc/os-release
    case "${ID:-}${ID_LIKE:-}" in
      *debian*|*ubuntu*) echo debian; return ;;
      *fedora*|*rhel*)   echo fedora; return ;;
      *arch*)            echo arch;   return ;;
    esac
  fi
  echo unknown
}

# --- FreeCAD user Mod (workbench) directory ------------------------------
# FreeCAD 1.1 -> ~/.local/share/FreeCAD/v1-1/Mod
# FreeCAD 1.0 -> ~/.local/share/FreeCAD/Mod
# 0.20/0.21   -> ~/.local/share/FreeCAD/Mod  (or ~/.FreeCAD/Mod on old builds)
# AppImage    -> same XDG dir; Snap/Flatpak differ (see Install-Guide).
fab_freecad_mod_dir() {
  [ -n "${FREECAD_MOD_DIR:-}" ] && { echo "$FREECAD_MOD_DIR"; return; }
  local base="$HOME/.local/share/FreeCAD"
  # 1) reuse an existing versioned Mod dir if present
  local existing
  existing="$(ls -d "$base"/v*/Mod 2>/dev/null | sort -V | tail -1)"
  [ -n "$existing" ] && { echo "$existing"; return; }
  [ -d "$base/Mod" ] && { echo "$base/Mod"; return; }
  # 2) derive from the running binary's version (e.g. 1.1 -> v1-1)
  local ver
  ver="$(timeout 25 freecad -c "import FreeCAD as A;print('FCVER',A.Version()[0]+'.'+A.Version()[1])" 2>/dev/null \
         | sed -n 's/^FCVER //p' | head -1)"
  if [ -n "$ver" ]; then
    local major="${ver%%.*}"
    if [ "$major" -ge 1 ] 2>/dev/null; then
      echo "$base/v${ver/./-}/Mod"; return        # 1.1 -> v1-1
    fi
  fi
  echo "$base/Mod"                                  # safe default
}

# --- Blender user add-ons directory --------------------------------------
# ~/.config/blender/<X.Y>/scripts/addons  (Snap/Flatpak differ -- see docs)
fab_blender_addon_dir() {
  [ -n "${BLENDER_ADDON_DIR:-}" ] && { echo "$BLENDER_ADDON_DIR"; return; }
  local d
  d="$(ls -d "$HOME"/.config/blender/*/scripts/addons 2>/dev/null | sort -V | tail -1)"
  [ -n "$d" ] && { echo "$d"; return; }
  # derive from version, fall back to a sane recent dir
  local ver
  ver="$(blender --version 2>/dev/null | sed -n 's/^Blender \([0-9]*\.[0-9]*\).*/\1/p' | head -1)"
  echo "$HOME/.config/blender/${ver:-4.2}/scripts/addons"
}

# --- BambuStudio binary / AppImage ---------------------------------------
# NixOS: /run/current-system/sw/bin/bambu-studio
# Ubuntu: usually an AppImage in ~/Applications or ~/.local/bin, or `bambu-studio`
fab_slicer_path() {
  [ -n "${SLICER_PATH:-}" ] && { echo "$SLICER_PATH"; return; }
  local p
  p="$(command -v bambu-studio 2>/dev/null)" && { echo "$p"; return; }
  p="$(command -v BambuStudio 2>/dev/null)" && { echo "$p"; return; }
  # common AppImage locations on Ubuntu
  for cand in "$HOME"/Applications/Bambu*Studio*.AppImage \
              "$HOME"/.local/bin/Bambu*Studio*.AppImage \
              "$HOME"/Downloads/Bambu*Studio*.AppImage; do
    [ -e "$cand" ] && { echo "$cand"; return; }
  done
  echo ""   # not found
}
