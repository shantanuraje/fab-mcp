#!/usr/bin/env bash
# fab-mcp :: bootstrap-ubuntu -- install the core stack on Ubuntu 22.04 / 24.04.
# NixOS users do NOT run this -- declare packages in configuration.nix instead.
#
# Installs: freecad, blender, nodejs, npm, git, curl (apt) and uv/uvx (astral).
# BambuStudio is NOT in apt; it's an AppImage from the Bambu Lab site -- this
# script only points you to it.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/_detect.sh"

OS="$(fab_detect_os)"
if [ "$OS" != "debian" ]; then
  echo "This bootstrap targets Ubuntu/Debian. Detected: $OS. Aborting."
  echo "On NixOS, add the packages to your NixOS configuration and run nixos-rebuild instead."
  exit 1
fi

echo "==> apt packages (freecad blender nodejs npm git curl)"
sudo apt update
sudo apt install -y freecad blender nodejs npm git curl

# uv / uvx via the official installer (apt's is often too old / absent)
if ! command -v uv >/dev/null 2>&1; then
  echo "==> installing uv (astral.sh)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # shellcheck disable=SC1090
  [ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env"
  echo "  uv installed to ~/.local/bin -- ensure it's on PATH (restart shell if needed)."
fi

echo
echo "==> versions"
for t in freecad blender node npm uv; do
  printf "  %-10s " "$t"; command -v "$t" >/dev/null 2>&1 && "$t" --version 2>&1 | head -1 || echo "MISSING"
done

echo
echo "BambuStudio (optional, for slicing): download the AppImage from"
echo "  https://bambulab.com/en/download/studio  -> chmod +x -> put in ~/Applications/"
echo "Then fab-mcp will auto-detect it via scripts/_detect.sh (fab_slicer_path)."
echo
echo "Next: bash scripts/setup.sh"
