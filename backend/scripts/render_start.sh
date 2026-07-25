#!/usr/bin/env bash
# Render / local start: Postgres → alembic; SQLite → optional seed dump.
# Prefer a venv that can import app deps (Render may put packages in $VIRTUAL_ENV).
set -euo pipefail
cd "$(dirname "$0")/.."

export PATH="${HOME}/.local/bin:${PATH}"

pick_python() {
  local candidate
  for candidate in \
    .venv/bin/python \
    "${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}" \
    python3
  do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if "$candidate" -c "import guidebridge" 2>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

ensure_deps() {
  local py
  if py="$(pick_python)"; then
    PYTHON="$py"
    return 0
  fi

  echo "guidebridge missing — installing deps with uv"
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
  unset VIRTUAL_ENV
  uv sync --frozen --all-extras --no-dev
  PYTHON=".venv/bin/python"
  "$PYTHON" -c "import guidebridge"
}

ensure_deps

is_postgres() {
  case "${DATABASE_URL:-}" in
    postgres://*|postgresql://*|postgresql+psycopg://*) return 0 ;;
    *) return 1 ;;
  esac
}

if is_postgres; then
  echo "Postgres detected — running alembic upgrade head"
  "$PYTHON" -m alembic upgrade head
else
  SEED="${SEED_DB_PATH:-./seed/hituto-c7c2dd3.db}"
  TARGET="${DATABASE_PATH:-./hituto.db}"
  if [[ -f "$SEED" ]]; then
    if [[ "${FORCE_RESEED:-0}" == "1" || ! -f "$TARGET" ]]; then
      echo "Seeding database from $SEED -> $TARGET (FORCE_RESEED=${FORCE_RESEED:-0})"
      cp "$SEED" "$TARGET"
    fi
  fi
fi

exec "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8077}"
