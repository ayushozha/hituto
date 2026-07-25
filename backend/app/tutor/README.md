# tutor — text teaching agent

Answers a learner's questions about the current lesson via LLM **function-calling**. The model's
tool call is Pydantic-validated server-side and the frontend renders it as a **trusted React
widget** — the model's raw output never reaches the app DOM. Streams over SSE (AG-UI frames).

## Flow

```
POST /courses/{cid}/lessons/{lid}/tutor/chat[/stream]   (api/v1/tutor.py)
  → build_tutor_context()          metadata + rag.get_lesson_context() (pack-first) + artifact digest
  → run_tutor_chat()               LangGraph single node (agent.py) → client.py
    → OpenAI-compatible /chat/completions with _TOOL_DEFS
    → take tool_calls[0]; validate (render_ui) or fail closed to text
  → response: {role, content, tool_call?}   (or SSE frames on /stream)
```

Streaming (`stream.py`) emits AG-UI frames: `RUN_STARTED`, `TEXT_MESSAGE_CONTENT{delta}`,
`TOOL_CALL_START/ARGS/END`, `RUN_FINISHED|RUN_ERROR`. `render_ui` args stream; `generate_ui` HTML
is never streamed (only the final `ui_id`).

## Tools (`tools/__init__.py`, `_TOOL_DEFS`)

Two rendering paths plus widget shortcuts:

- **`render_ui` — trusted A2UI tree** (the preferred path). A declarative component tree validated
  by `a2ui/` (`normalize_render_ui`, max 6 levels / 60 nodes): `stack, heading, text, callout,
  math, steps, quiz, table, chart, slider, diagram`. Invalid → `None` → falls back to text
  (fail-closed). Rendered by the frontend `A2UIRenderer`.
- **`generate_ui` — untrusted HTML escape hatch.** A self-contained HTML doc for things A2UI can't
  express. Run through the **capsule security gate** (`capsule/postprocess.py`) and stored in the
  ephemeral UI store (`capsule/generative_ui.py`, 30-min TTL, owner+lesson tagged); only a
  `ui_id` is returned. The iframe fetches it from `GET …/tutor/ui/{ui_id}` under the same CSP
  sandbox as lesson artifacts. Raw HTML never reaches the client directly.
- **Widget shortcuts:** `create_quiz`, `show_flashcards`, `show_code_exercise`, `create_game`,
  `show_diagram`, `show_formula_calculator`, `show_whiteboard` — each a Pydantic schema
  (`tools/widgets.py`). `show_whiteboard` embeds the Excalidraw viewer SPA via iframe.

## Lesson context (`context.py`)

`build_tutor_context()` reads course/lesson metadata + the latest `Artifact` digest
(`html_to_text`) and calls `rag.get_lesson_context()`, which returns one of three modes:
`chapter` (grounded by `LessonSourcePack.chapter_ids`), `retrieve` (live two-stage search over the
teaching map), or `none` (web-only). Excerpts carry page/section provenance for grounded answers.

## Data model touched

**Read-only.** `Course`, `Lesson`, latest `Artifact` (digest), and RAG tables via
`rag.get_lesson_context` (`LessonSourcePack`, `SourceChunk`). Writes nothing durable (the
`generate_ui` store is in-memory). See [`../../DATABASE.md`](../../DATABASE.md).

## Config

LLM via `LLM_*` with optional `TUTOR_LLM_*` override. LangSmith tracing optional
(`LANGSMITH_TRACING`, tag `agent:tutor`), never required.

## Key files

`agent.py` (LangGraph node) · `client.py` (LLM call + fail-closed tool parsing) ·
`tools/__init__.py` + `tools/widgets.py` + `tools/generate_ui.py` · `stream.py` (AG-UI SSE) ·
`context.py` · `prompts_util.py`. Routes: `api/v1/tutor.py`. Schemas: `schemas/tutor.py`.
Shared: `a2ui/schema.py` + `a2ui/normalize.py`, `capsule/generative_ui.py`.

## Tests

`test_render_ui.py`, `test_generative_ui.py`, `test_tutor.py`, `test_tutor_stream.py`,
`test_tutor_context_pack_first.py`, `test_a2ui_catalogue_sync.py`.
