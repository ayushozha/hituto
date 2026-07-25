#!/usr/bin/env bash
# Render build: install deps with uv into this project's .venv.
# Unset VIRTUAL_ENV so packages land in backend/.venv (not Render's repo-root venv).
set -euo pipefail
cd "$(dirname "$0")/.."

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="${HOME}/.local/bin:${PATH}"
unset VIRTUAL_ENV

# Prefer the interpreter Render already provisioned (PYTHON_VERSION / path).
if command -v python3 >/dev/null 2>&1; then
  uv sync --python "$(command -v python3)" --frozen --all-extras --no-dev
else
  uv python install 3.12
  uv sync --python 3.12 --frozen --all-extras --no-dev
fi

.venv/bin/python -c "import guidebridge, fastapi; print('deps ok')"
