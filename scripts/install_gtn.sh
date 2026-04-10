#!/usr/bin/env bash
set -euo pipefail

GTN_HOME="${GTN_HOME:-$HOME/.gtn}"
VENV_DIR="$GTN_HOME/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
GLOBAL_BIN_DIR="${GLOBAL_BIN_DIR:-$HOME/.local/bin}"
GTN_WRAPPER="$GLOBAL_BIN_DIR/gtn"
PACKAGE_NAME="${PACKAGE_NAME:-goodtoknow-gtn}"
PACKAGE_REF="${PACKAGE_REF:-$PACKAGE_NAME}"

UV_BIN="${UV_BIN:-$(command -v uv || true)}"
if [[ -z "$UV_BIN" ]]; then
  echo "uv not found on PATH. Please install uv first (for example: brew install uv)." >&2
  exit 1
fi

mkdir -p "$GLOBAL_BIN_DIR" "$GTN_HOME/runs" "$GTN_HOME/logs"

"$UV_BIN" venv "$VENV_DIR"
"$UV_BIN" pip install --python "$VENV_PYTHON" "$PACKAGE_REF"

CODEX_PATH="$(command -v codex || true)"
if [[ -z "$CODEX_PATH" ]]; then
  echo "codex not found on PATH; install/init Codex first" >&2
  exit 1
fi

cat > "$GTN_WRAPPER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$VENV_PYTHON" -m runtime.gtn_local_product "\$@"
EOF
chmod +x "$GTN_WRAPPER"

"$GTN_WRAPPER" init --codex-path "$CODEX_PATH"

RUNTIME_ROOT="$GTN_HOME/runtime/GoodToKnow"
NOTION_SETTINGS="$RUNTIME_ROOT/output/notion-briefing/settings.json"
NOTION_PAGE_URL="${GTN_NOTION_PAGE_URL:-}"

if [[ -z "$NOTION_PAGE_URL" && -t 0 ]]; then
  cat <<'EOF'

Notion setup
------------
To view recommendations in Notion:
1. Create a new empty Notion page named "GoodToKnow" (or any page you want to use).
2. Make sure your Codex/Notion MCP access can reach that workspace.
3. Paste the page URL below.

Leave it blank to skip for now. You can configure it later by editing:
~/.gtn/runtime/GoodToKnow/output/notion-briefing/settings.json
EOF
  printf "Notion page URL: "
  read -r NOTION_PAGE_URL
fi

if [[ -n "$NOTION_PAGE_URL" ]]; then
  "$VENV_PYTHON" - <<PY
import json
from pathlib import Path
path = Path("$NOTION_SETTINGS")
payload = json.loads(path.read_text(encoding="utf-8"))
payload["parent_page_url"] = "$NOTION_PAGE_URL"
payload["database_url"] = ""
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
PY
fi

USER_PROFILE="${GTN_USER_PROFILE:-}"
if [[ -z "$USER_PROFILE" && -t 0 ]]; then
  cat <<'EOF'

About you
---------
Please describe yourself in a few lines so GoodToKnow can make better recommendations.
Try to include:
- your interests
- the main kinds of work you do on this computer
- any recurring topics you care about

Finish by entering an empty line.
EOF
  PROFILE_LINES=()
  while IFS= read -r line; do
    [[ -z "$line" ]] && break
    PROFILE_LINES+=("$line")
  done
  if [[ ${#PROFILE_LINES[@]} -gt 0 ]]; then
    USER_PROFILE="$(printf '%s\n' "${PROFILE_LINES[@]}")"
  fi
fi

if [[ -n "$USER_PROFILE" ]]; then
  "$VENV_PYTHON" "$RUNTIME_ROOT/memory/mempalace-memory/scripts/record_user_profile.py" "$USER_PROFILE"
fi

echo "GTN installed from package: $PACKAGE_REF"
echo "GTN runtime: $RUNTIME_ROOT"
echo "GTN command: $GTN_WRAPPER"
if [[ ":$PATH:" != *":$GLOBAL_BIN_DIR:"* ]]; then
  echo "Warning: $GLOBAL_BIN_DIR is not currently on PATH."
  echo "Add it to PATH, then you can run: gtn status"
else
  echo "You can now run: gtn status"
fi
if [[ -n "$NOTION_PAGE_URL" ]]; then
  echo "Configured Notion parent page: $NOTION_PAGE_URL"
else
  echo "Notion parent page not configured yet."
fi
if [[ -n "$USER_PROFILE" ]]; then
  echo "Recorded initial user profile into memory."
else
  echo "User profile not recorded yet."
fi
