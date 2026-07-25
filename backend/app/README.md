# Hi Tuto backend — architecture

FastAPI + LangGraph backend for a generative learning platform. A signed-in learner enters a
topic (or uploads a PDF/Markdown/text source) and gets a locked 5-lesson roadmap; lessons are
generated **just-in-time** as interactive HTML **capsules** rendered in a CSP-locked sandboxed
iframe. A text **tutor** and a **voice** instructor teach on top of the running capsule.

## Layout — agents + shared protocols + platform

```
app/
├── coursegen/   AGENT · syllabus + lesson generation (LangGraph today; Deep Agent flag-gated)
├── tutor/       AGENT · text teaching via LLM function-calling → validated tool calls (SSE)
├── voice/       AGENT · OpenAI Realtime S2S instructor that observes + drives the capsule
├── rag/         PROTOCOL · ingest, retrieve, citations, lesson/chapter context
├── a2ui/        PROTOCOL · render_ui schema + catalogue (trusted declarative widgets)
├── capsule/     PROTOCOL · postprocess security gate, CSP, injected lesson bridge
├── models/      data model (Course → Lesson → Artifact + document-grounding tables)
├── services/    api/v1 → services → models (projections, orchestration)
├── api/v1/       thin HTTP/WS/SSE routes
├── providers/   live provider adapters (LLM, search, media, mesh) — fakes in tests
└── core/        config, db, auth, progress (SSE broker), checkpoint (LangGraph HITL)
```

**Import rule:** agents (`coursegen`/`tutor`/`voice`) never cross-import; protocols
(`rag`/`a2ui`/`capsule`) never import agents. Enforced by `tests/test_import_boundaries.py`.

## READMEs

| Doc | What |
|---|---|
| [`coursegen/README.md`](coursegen/README.md) | Syllabus + lesson generation; LangGraph pipeline + the flag-gated Deep Agent |
| [`tutor/README.md`](tutor/README.md) | Text tutor: function-calling → A2UI widgets + the `generate_ui` HTML escape hatch |
| [`voice/README.md`](voice/README.md) | Voice instructor (OpenAI Realtime S2S) + page control via the lesson bridge |
| [`rag/README.md`](rag/README.md) | Document ingest → teaching map → retrieval → grounding |
| [`capsule/README.md`](capsule/README.md) | The untrusted-HTML security gate, CSP, and the host↔capsule bridge |
| [`../DATABASE.md`](../DATABASE.md) | Data model, ownership, persistence, and Alembic migrations |

> These READMEs supersede the Kiro-style design specs that lived in `specs-tmp/`. They are
> grounded in the current code; see git history + `AGENTS.md` for deeper background.
