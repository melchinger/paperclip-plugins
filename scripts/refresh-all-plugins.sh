#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_SCRIPT="$ROOT_DIR/scripts/install-plugin.sh"
PLUGINS_DIR="$ROOT_DIR/plugins"

if [[ ! -x "$INSTALL_SCRIPT" ]]; then
  chmod +x "$INSTALL_SCRIPT"
fi

mapfile -t PLUGIN_DIRS < <(find "$PLUGINS_DIR" -mindepth 1 -maxdepth 1 -type d | sort)

if [[ ${#PLUGIN_DIRS[@]} -eq 0 ]]; then
  echo "No plugin directories found under $PLUGINS_DIR" >&2
  exit 1
fi

for dir in "${PLUGIN_DIRS[@]}"; do
  name="$(basename "$dir")"
  "$INSTALL_SCRIPT" "$name" --no-restart
done

systemctl restart paperclip
echo "Refreshed ${#PLUGIN_DIRS[@]} plugins and restarted paperclip.service"
