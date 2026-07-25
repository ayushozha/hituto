# coursegen — syllabus + lesson generation agent

Turns a topic (or an uploaded document) into a locked roadmap of lessons, and generates each
lesson as a self-contained interactive HTML **capsule**. Public entry is `coursegen/run.py`
(`run_generation`, `run_syllabus_planning`) — used by `services/`.

## Two engines (important)

Lesson generation has **two implementations behind one entry point**, selected by
`DEEP_AGENTS_ENABLED` (default **off**):

- **LangGraph pipeline (`graph.py`) — the default, production path.** A deterministic 6-stage
  state machine. This is what runs unless the flag is on.
- **Deep Agent (`agents/lesson_agent.py`) — flag-gated.** A `deepagents.create_deep_agent`
  orchestrator that delegates to subagents. It attempts a lesson and **falls back to the graph**
  on any unsupported case or failure, so the graph is always the safety net.

`agents/orchestrator.py::run_generation_via_orchestrator` is the switch: if the flag is on it
tries the Deep Agent, else (or on failure) it runs `graph.run_generation`.

## LangGraph pipeline (`graph.py`)

```
interpret → research → asset_plan → generate → post_process → persist
                                       ↑___________|  (repair loop, up to MAX_GEN_RETRIES)
```

- **interpret** — load course/lesson, build the lesson plan (`planner.build_lesson_plan`).
- **research** — document-grounded → `rag.get_lesson_context` (pack-first); else web search.
- **asset_plan** — best-effort compute (`sandbox.run_viz_lab`) + mesh (`agents/roles/mesh_viz`),
  routed through the subject specialist (`agents/registry.py`).
- **generate** — LLM authors the capsule from `prompts/lesson_system.md` + `prompt.py` blocks
  (or A2UI JSON when `COURSEGEN_A2UI_LESSONS=1`).
- **post_process** — `capsule/postprocess.py` security+quality gate; grounding validation.
- **persist** — `graph.persist_artifact()` writes the versioned `Artifact` (+ citations + source
  pack), inlines compute/mesh assets, and emits the terminal SSE event. Teacher **HITL** pauses
  here via a durable LangGraph `interrupt()` (`core/checkpoint.py`).

## Deep Agent (`agents/lesson_agent.py`)

A `create_deep_agent` orchestrator (`prompts/agents/orchestrator.md`) that delegates via the
built-in `task` tool to a roster assembled per lesson:

```
orchestrator
  └─ researcher            web_search
     ├─ data_synthesizer   synthesize_dataset      ┐ compute archetypes
     ├─ viz_engineer        run_viz_lab             ┘ (simulation/game/tool)
     ├─ mesh_viz            generate_studio_meshes  · studio lessons
     ├─ <subject>_specialist  check_katex / viz / mesh · maths & science (routed)
     ├─ capsule_author      write_file → /build/capsule.html (+ ui-studio-style shell)
     └─ qa_reviewer         capsule_checks
  → host reads /build/capsule.html → postprocess gate → persist_artifact (compute/mesh inlined)
```

- Subagents hand off via a scratch filesystem (default `StateBackend`), not chat history.
- Tools (`agents/tools.py`) wrap existing coursegen/rag/capsule functions; they return JSON
  summaries and write large artifacts (plots/meshes) to scratch, never into chat.
- **Deferred to the graph:** document-grounded lessons, teacher-review (HITL) lessons, and any
  archetype outside `explainer/narrative/simulation/game/tool`.
- **Follow-ups (not yet built):** agent-native `interrupt_on` HITL (currently defers to the graph
  HITL) and loading skills onto the lesson agent via the deepagents backend (studio guidance is
  injected directly today; the *syllabus* agent already uses the skills backend).

The **syllabus** Deep Agent (`agents/syllabus_planner.py`) is separate and also flag-gated, with a
deterministic fallback (`planner.build_syllabus` / teaching-map). It loads `skills/core` +
subject skills via a `FilesystemBackend`.

## Presentation shells (`presentation.py`)

`resolve_presentation` picks `page` (default), `studio` (a stage-first interactive lab), or `slide`.
An explicit knob wins; else `needs_3d`/a spatial regex selects `studio`. For an initial Studio
lesson, `studio_manifest.py` routes the topic to `specimen`, `simulation`, or `process-cutaway`,
validates the typed manifest, and `studio_renderer.py` renders the server-owned shell from
`skills/ui-studio-style`. Free-form Studio HTML remains available only for refinements.

## Mesh / 3D (`mesh.py`, `agents/roles/mesh_viz.py`, `providers/mesh.py`)

Hunyuan 3D meshes (Tencent preferred; GMI/Atlas fallbacks) are reserved for specimen Studio
lessons. Simulation and process-cutaway modes use deterministic procedural adapters instead.
Mesh requests are best-effort and cost-gated by `MESH_STUDIO_MAX_HUNYUAN`; GLBs cache on disk and
serve via same-origin `/mesh?key=` (rewritten at persist). Missing credentials never fail
generation — the capsule renders a procedural fallback.

## Skills (`skills/**/SKILL.md`)

Prompt guidance (core pedagogy/grounding, per-subject, visualization/simulation/data-synthesis,
`ui-studio-style`, `ui-slide-deck`, `hunyuan-3d`). The LangGraph path paraphrases the relevant
blocks inline via `prompt.py`; the Deep Agents path loads them through the deepagents skills
backend (syllabus agent) or injects them directly (studio shell on the lesson agent).

## Data model touched

Writes `Artifact` (versioned `html`/`a2ui`), `Citation`, `LessonSourcePack`; updates
`Lesson.status` / `Course.status`. Reads `Course`/`Lesson`/`knobs`. See [`../../DATABASE.md`](../../DATABASE.md).

## Config flags

`DEEP_AGENTS_ENABLED` (off), `COURSEGEN_A2UI_LESSONS` (off), `SANDBOX_PROVIDER` (none),
`MESH_STUDIO_MAX_HUNYUAN`, `require_teacher_review` (per-course knob). LLM via `LLM_*` with
optional `COURSEGEN_LLM_*` override.

## Key files

`run.py` (façade) · `graph.py` (pipeline + `persist_artifact`) · `planner.py` · `prompt.py` +
`prompts/` · `presentation.py` · `mesh.py` / `studio_catalog.py` · `agents/orchestrator.py` ·
`agents/lesson_agent.py` · `agents/syllabus_planner.py` · `agents/registry.py` ·
`agents/tools.py` · `agents/specialists.py` · `agents/roles/*` · `agents/prompt_loader.py`.

## Tests

`test_coursegen_deep_agent_lesson.py`, `test_syllabus_deep_agent.py`,
`test_coursegen_orchestrator_fallback.py`, `test_stub_pipeline.py`, `test_compute_artifact.py`,
`test_presentation.py`, `test_studio_catalog.py`, `test_mesh_*.py`, `test_teacher_hitl.py`.
