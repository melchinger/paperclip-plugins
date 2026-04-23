#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGINS_DIR="$ROOT_DIR/plugins"
RUNTIME_DIR="/var/lib/paperclip/.paperclip/plugins"
CONFIG_PATH="/var/lib/paperclip/instances/default/config.json"

usage() {
  cat <<'EOF'
Usage:
  install-plugin.sh <plugin-dir-name> [--no-restart]

Example:
  install-plugin.sh zip-issue-expander
  install-plugin.sh paperclip-issue-archiver --no-restart
EOF
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 1
fi

PLUGIN_DIR_NAME=""
RESTART_SERVICE=1

for arg in "$@"; do
  case "$arg" in
    --no-restart)
      RESTART_SERVICE=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -n "$PLUGIN_DIR_NAME" ]]; then
        echo "Only one plugin directory name is supported." >&2
        exit 1
      fi
      PLUGIN_DIR_NAME="$arg"
      ;;
  esac
done

if [[ -z "$PLUGIN_DIR_NAME" ]]; then
  echo "Missing plugin directory name." >&2
  exit 1
fi

PLUGIN_DIR="$PLUGINS_DIR/$PLUGIN_DIR_NAME"
if [[ ! -d "$PLUGIN_DIR" ]]; then
  echo "Plugin directory not found: $PLUGIN_DIR" >&2
  exit 1
fi

if [[ ! -f "$PLUGIN_DIR/package.json" ]]; then
  echo "package.json not found in $PLUGIN_DIR" >&2
  exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Paperclip config not found: $CONFIG_PATH" >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "node is required" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required" >&2
  exit 1
fi

PLUGIN_PACKAGE_NAME="$(node -p "require('$PLUGIN_DIR/package.json').name")"

pushd "$PLUGIN_DIR" >/dev/null
rm -f ./*.tgz
npm pack >/dev/null
TARBALL_NAME="$(ls -1 ./*.tgz | head -n1)"
TARBALL_BASENAME="$(basename "$TARBALL_NAME")"
popd >/dev/null

pushd "$RUNTIME_DIR" >/dev/null
npm install --save "../../repos/melchinger/paperclip-plugins/plugins/$PLUGIN_DIR_NAME/$TARBALL_BASENAME" >/dev/null
popd >/dev/null

PACKAGE_PATH="$RUNTIME_DIR/node_modules/$PLUGIN_PACKAGE_NAME"

readarray -t PLUGIN_META < <(
  PLUGIN_DIR="$PLUGIN_DIR" node --input-type=module <<'JS'
import fs from "node:fs";
import path from "node:path";

const pluginDir = process.env.PLUGIN_DIR;
const pkg = JSON.parse(fs.readFileSync(path.join(pluginDir, "package.json"), "utf8"));
const manifestModule = await import(path.join(pluginDir, "dist", "manifest.js"));
const manifest = manifestModule.default;
console.log(pkg.name);
console.log(pkg.version);
console.log(manifest.id);
console.log(String(manifest.apiVersion ?? 1));
console.log(JSON.stringify(manifest.categories ?? []));
console.log(JSON.stringify(manifest));
JS
)

PKG_NAME="${PLUGIN_META[0]}"
PKG_VERSION="${PLUGIN_META[1]}"
PLUGIN_KEY="${PLUGIN_META[2]}"
API_VERSION="${PLUGIN_META[3]}"
CATEGORIES_JSON="${PLUGIN_META[4]}"
MANIFEST_JSON="${PLUGIN_META[5]}"

DATABASE_URL="$(python3 - <<'PY'
import json
from pathlib import Path
config = json.loads(Path("/var/lib/paperclip/instances/default/config.json").read_text())
print(config["database"]["connectionString"])
PY
)"

python3 - <<'PY' "$DATABASE_URL" "$PLUGIN_KEY" "$PKG_NAME" "$PACKAGE_PATH" "$PKG_VERSION" "$API_VERSION" "$CATEGORIES_JSON" "$MANIFEST_JSON"
import json
import subprocess
import sys

db, plugin_key, package_name, package_path, version, api_version, categories_json, manifest_json = sys.argv[1:]
payload = {
    "plugin_key": plugin_key,
    "package_name": package_name,
    "package_path": package_path,
    "version": version,
    "api_version": int(api_version),
    "categories": json.loads(categories_json),
    "manifest_json": json.loads(manifest_json),
}
doc = json.dumps(payload)
doc_sql = "'" + doc.replace("'", "''") + "'"
sql = """
with data as (
  select {doc_sql}::jsonb as doc
),
ins as (
  insert into public.plugins (
    id, plugin_key, package_name, package_path, version, api_version,
    categories, manifest_json, status, install_order, last_error, installed_at, updated_at
  )
  select
    gen_random_uuid(),
    doc->>'plugin_key',
    doc->>'package_name',
    doc->>'package_path',
    doc->>'version',
    (doc->>'api_version')::integer,
    doc->'categories',
    doc->'manifest_json',
    'ready',
    coalesce((select max(install_order) from public.plugins where install_order is not null), 0) + 1,
    null,
    now(),
    now()
 from data
 where not exists (
    select 1 from public.plugins where plugin_key = doc->>'plugin_key'
  )
)
update public.plugins p
   set package_name = data.doc->>'package_name',
       package_path = data.doc->>'package_path',
       version = data.doc->>'version',
       api_version = (data.doc->>'api_version')::integer,
       categories = data.doc->'categories',
       manifest_json = data.doc->'manifest_json',
       status = 'ready',
       last_error = null,
       updated_at = now()
  from data
 where p.plugin_key = data.doc->>'plugin_key';
""".format(doc_sql=doc_sql)
subprocess.run(
    ["psql", db, "-v", "ON_ERROR_STOP=1", "-c", sql],
    check=True,
)
PY

if [[ "$RESTART_SERVICE" -eq 1 ]]; then
  systemctl restart paperclip
fi

echo "Installed $PLUGIN_KEY from $PLUGIN_DIR"
if [[ "$RESTART_SERVICE" -eq 1 ]]; then
  echo "Restarted paperclip.service"
fi
