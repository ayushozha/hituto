# rag — document knowledge layer (protocol)

Turns an uploaded PDF/Markdown/text into structured, retrievable knowledge that coursegen and the
tutor use to ground lessons and answers. A **protocol** package: it never imports agents; agents
call its public functions.

## Pipeline: ingest → outline → teaching map → passages → embed

`ingest.py::save_and_ingest()` persists the upload (InsForge Storage or local disk) and spawns
`run_source_ingestion()`, which advances `SourceDocument.status` through six phases:

```
uploaded → parsing → outlining → mapping → chunking → indexing → ready | failed
```

1. **parse** — `liteparse_adapter.py` (LiteParse + PyMuPDF dual path) → canonical Markdown +
   manifest + figures. NUL bytes sanitized; text/markdown use a fallback adapter.
2. **outline** (`outline.py`) — a **deterministic** node tree from Markdown headings (never
   LLM-written); falls back to manifest headings, then paragraph groups under
   `RAG_SOURCE_UNIT_TOKENS` (1200).
3. **teaching map** (`teaching_map.py`) — LLM extracts chapters referencing outline node ids
   (`extract_teaching_map_llm`), validated by `validate_teaching_map`; deterministic fallback from
   top-level nodes. `materialize_chapter_md()` concatenates verbatim spans — no paraphrase.
4. **passages** (`passages.py`) — per chapter: a `chapter_summary` row + recursively split passage
   chunks (~1000 tokens, 150 overlap), tiktoken `cl100k_base`.
5. **embed** — pgvector on Postgres (`VECTOR_STORE=pgvector`); `None` on SQLite (keyword fallback).

`recover_orphaned_ingestions()` requeues docs stuck mid-pipeline after a restart.

## Retrieval (`retrieve.py`) & context (`context.py`)

Hybrid two-stage: `route_chapters()` ranks the 3 best teaching chapters, then
`retrieve_passages()` searches passages within them (pgvector cosine `<=>` + keyword fallback).
Pre-cutover docs fall back to keyword/vector over all chunks.

Public functions the agents call:
- `get_lesson_context()` — the main entry. Returns mode `chapter` (constrained to a lesson's
  `LessonSourcePack.chapter_ids`), `retrieve` (live over the whole teaching map), or `none`
  (web discovery). Used by coursegen `research` and the tutor/voice context builders.
- `get_chapter_context()` — full verbatim chapter Markdown (+ summary, thesis, neighbor titles,
  figure keys). Callers split if needed — no blind truncation.
- `search_source_pack()`, `retrieve_passages()`, `resolve_visual_candidates()`.

## Grounding (`citations.py`)

`check_grounding()` — deterministic, offline: flags missing citations, foreign citations, and
verbatim copying (18-word window). `build_repair_brief()` feeds the coursegen repair loop.
`review_grounding()` is an optional model-assisted reviewer; never blocks.

## Data model

`SourceDocument` (status, `source_map` JSON: parse/outline/teaching_map/sections),
`SourceChunk` (text + page/section + `embedding` + `chunk_meta`), `CourseSource` (course↔doc link),
`LessonSourcePack` (per-lesson grounding evidence: `chunk_ids`/`chapter_ids`/`passage_ids` +
citations). See [`../../DATABASE.md`](../../DATABASE.md).

## Config

`DOC_GROUNDED_ENABLED` (on), `VECTOR_STORE` (keyword|pgvector), `RAG_LITEPARSE_ENABLED`,
`RAG_OCR_ENABLED`, `RAG_TREE_ENABLED`, `RAG_TEACHING_MAP_PLANNER`, `RAG_CHAPTER_EMBED`, token
windows (`RAG_SOURCE_UNIT_TOKENS`, `RAG_LESSON_CONTEXT_TOKENS`, …). Embeddings via `EMBEDDING_*`.

## Key files

`ingest.py` · `liteparse_adapter.py` · `outline.py` · `teaching_map.py` · `passages.py` ·
`retrieve.py` · `context.py` · `citations.py` · `ensure.py` (lazy legacy upgrade) · `service.py`.

## Tests

`test_ingest.py`, `test_liteparse.py`, `test_outline_teaching_map.py`, `test_passages_retrieve.py`,
`test_teaching_map_planner.py`, `test_grounding.py`, `test_retrieval.py`, `test_graph_retrieval.py`,
`test_rag_context.py`, `test_document_shapes.py`, `test_ingestion_recovery.py`, `test_pgvector.py`.
