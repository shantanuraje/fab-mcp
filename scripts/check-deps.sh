#!/usr/bin/env bash
# fab-mcp :: check-deps -- verify every tool the MCP stack needs is present.
# Read-only. Distro-aware install hints (NixOS / Ubuntu-Debian / other).
# Exits non-zero if a required tool is missing.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/_detect.sh"

OS="$(fab_detect_os)"
req=(freecad blender uv uvx node npx)              # required for the core stack
opt=(bambu-studio claude codex opencode gemini git curl)  # agents / nice-to-have
missing=0

echo "fab-mcp dependency check   (os: $OS)"
echo "===================================="
check() {
  local name="$1" kind="$2"
  if command -v "$name" >/dev/null 2>&1; then
    printf "  [ok]   %-14s %s\n" "$name" "$(command -v "$name")"
  else
    printf "  [MISS] %-14s (%s)\n" "$name" "$kind"
    [ "$kind" = required ] && missing=$((missing+1))
  fi
}

echo "Core stack:"
for t in "${req[@]}"; do check "$t" required; done
echo "Agents / optional:"
for t in "${opt[@]}"; do check "$t" optional; done

echo
if [ "$missing" -eq 0 ]; then
  echo "OK: all required tools present."
  exit 0
fi

echo "FAIL: $missing required tool(s) missing. Install hints for '$OS':"
case "$OS" in
  nixos)
    echo "  Add them to your NixOS configuration (configuration.nix or your flake) and rebuild:"
    echo "    environment.systemPackages = with pkgs; [ freecad blender uv nodejs bambu-studio ];"
    echo "    sudo nixos-rebuild switch"
    ;;
  debian)
    echo "  Run the bootstrap helper:  bash scripts/bootstrap-ubuntu.sh"
    echo "  Or manually:"
    echo "    sudo apt update"
    echo "    sudo apt install -y freecad blender nodejs npm git curl"
    echo "    curl -LsSf https://astral.sh/uv/install.sh | sh   # uv + uvx"
    echo "  (BambuStudio on Ubuntu ships as an AppImage from the Bambu Lab site.)"
    ;;
  *)
    echo "  uv:      curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "  node:    use your distro package manager or nvm"
    echo "  freecad/blender/bambu-studio: distro packages, AppImage, or flatpak"
    ;;
esac
exit 1
