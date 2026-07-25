# Contributing (Hi Tuto)

Hi Tuto is a hackathon project. Keep changes focused and consistent with the
existing stack.

When working in this codebase:

- Python: 4-space indentation, 100-character line limit (`ruff check`).
- Put new backend tests under `backend/tests/` as `test_*.py`.
- Respect import boundaries (API → services → agents/protocol/infra). Agents must
  never import each other; protocol packages must never import an agent.
- Frontend UI work should follow the design system in `ui_ux_design/`.
