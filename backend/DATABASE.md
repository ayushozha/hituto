# Data model & persistence

SQLAlchemy ORM (`app/models/`). Every row is scoped to a `user_id`; the core hierarchy is
**Course → Lesson → Artifact**, with a parallel set of tables for document grounding.

## Core tables (`models/course.py`)

| Table | Key columns | Relationships | Written by |
|---|---|---|---|
| **courses** | `id`, `user_id`, `topic`, `title`, `knobs` (JSON), `archetype`, `status`, `cover_prompt` | 1→N `lessons`, 1→N `citations` (cascade) | coursegen (create), `course_service` (project) |
| **lessons** | `id`, `course_id`→courses, `ordinal`, `title`, `objective`, `status`, `share_token` (unique), `archetype`, `completed` | N←course, 1→N `artifacts` | coursegen (generate), HITL (`awaiting_review`), `course_service` |
| **artifacts** | `id`, `lesson_id`→lessons, `version`, `kind` (`html`\|`a2ui`), `html`, `a2ui` (JSON), `checks` (JSON) | N←lesson | coursegen (versioned; never overwritten — regen adds a version) |
| **citations** | `id`, `course_id`→courses, `claim`, `source_url` | N←course | coursegen (research) |
| **generation_runs** | `id`, `course_id`→courses, `stage_timings` (JSON), `status` | N←course | coursegen (async progress) |

`knobs` holds the generation config (`difficulty`, `presentation`, `archetype`, `needs_3d`,
`subject`, `require_teacher_review`, `source_document_id`, `lesson_scopes`, …).

## Document-grounding tables (`models/source.py`)

| Table | Key columns | Relationships | Written by |
|---|---|---|---|
| **source_documents** | `id`, `user_id`, `filename`, `mime_type`, `status`, `title`, `page_count`, `extraction_quality` (JSON), `source_map` (JSON), `full_text` | 1→N `source_chunks`, `course_sources`, `lesson_source_packs` | rag.ingest (parse/chunk), rag.ensure (teaching map) |
| **source_chunks** | `id`, `source_document_id`→docs, `user_id`, `chunk_index`, `page_start/end`, `heading_path` (JSON), `text`, `token_count`, `embedding` (VectorColumn), `chunk_meta` (JSON) | N←doc | rag.ingest; embedded async when pgvector |
| **course_sources** | `id`, `course_id`→courses, `source_document_id`→docs, `selected_sections` (JSON), `mode` | join | `source_service` (course-from-source) |
| **lesson_source_packs** | `id`, `lesson_id`→lessons, `source_document_id`→docs, `chunk_ids`/`chapter_ids`/`passage_ids` (JSON), `retrieval_query`, `citations` (JSON) | join | rag.context (grounding at gen time), read by tutor/UI |

`source_map` (JSON on the document) holds the derived structure: `parse` (extraction metadata),
`document_outline` (deterministic node tree), `teaching_map` (chapters → passages), and legacy
`sections`. `lesson_source_packs.chapter_ids`/`passage_ids` soft-reference these.

## Ownership

Everything is owned by `user_id` (top-level index on `courses`/`source_documents`; children
inherit via FK). Deleting a course cascades to its lessons/artifacts/citations. Public **share
links** are the one exception: `lessons.share_token` is an unguessable token that grants
anonymous read-only access with no ownership check (`api/v1/shared.py`). Auth (`core/auth.py`)
verifies an InsForge JWT (HS256 with `INSFORGE_JWT_SECRET`) → `user_id`, or uses
`DEV_USER="dev"` when `AUTH_DISABLED=1`.

## Persistence & config (`core/`)

- **`db.py`** — `SessionLocal`, engine, `init_db()` (`create_all` + `_ensure_added_columns`, a
  poor-man's SQLite column upgrade). Tests monkeypatch `SessionLocal` onto an isolated DB.
- **Dev:** SQLite (`DATABASE_URL=sqlite:///./hituto.db`). **Prod:** any Postgres URL
  (`postgresql+psycopg://…`) with Alembic migrations in `alembic/versions/` (initial schema,
  pgvector column, `share_token`, artifact `a2ui`, source-pack `chapter_ids`, `awaiting_review`).
- **`vectortype.py`** — `VectorColumn` toggles by dialect: pgvector `Vector(dim)` on Postgres,
  JSON list on SQLite. `VECTOR_STORE=pgvector` enables semantic retrieval (default `keyword`).
- **`checkpoint.py`** — LangGraph durable checkpointer (`AsyncSqliteSaver`, `hituto.langgraph.db`)
  for teacher-review HITL; thread id `lesson-gen:{lesson_id}`. Recreated per event loop.
- **`progress.py`** — in-memory SSE broker (`ProgressEvent{stage,detail,pct}`), process-local /
  single-worker; keeps the last event per course so late subscribers catch up.
- **Uploads** — InsForge Storage when `INSFORGE_API_KEY` is set, else local-disk `UPLOAD_DIR` (tests force
  the fallback). Mesh GLBs → `MESH_STORAGE_BUCKET`.

## Layering

`api/v1/` (thin routes) → `services/` (projections + orchestration) → `models/`. Route modules:
`courses.py` (CRUD, artifacts, share, SSE, source packs), `sources.py` (upload, outline,
course-from-source), `tutor.py` (chat SSE + `generate_ui`), `voice.py` (Realtime WS),
`tools.py` (`/gen`,`/image`,`/audio`,`/mesh`,`/maps`), `shared.py` (public share tokens).
Lifespan (`main.py`) runs `init_db()`, validates providers, and requeues orphaned
generations/ingestions on restart.
