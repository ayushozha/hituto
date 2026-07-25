"""Runtime configuration, loaded from environment / .env.

Loads `backend/.env` only. Accepts MVP 1 names (`PROVIDER_LLM`,
`NEBIUS_API_BASE_URL`, …) as aliases for MVP 2 fields.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> parents: [0]=core [1]=app [2]=backend [3]=repo root
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_ROOT / ".env"
ACTIVE_VOICE_PROVIDER = "openai_realtime_s2s"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- generation model (single OpenAI-compatible client) ---
    # Default: Anthropic's OpenAI-compatible endpoint
    # (https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk).
    # Any OpenAI-compatible backend works — swap via base URL + key + model.
    # GMI_*/NEBIUS_* aliases keep older env files working unchanged.
    llm_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices("LLM_PROVIDER", "PROVIDER_LLM"),
    )  # openai-compatible live client
    llm_base_url: str = Field(
        default="https://api.anthropic.com/v1",
        validation_alias=AliasChoices(
            "LLM_BASE_URL", "GMI_BASE_URL", "GMI_API_BASE_URL",
            "NEBIUS_BASE_URL", "NEBIUS_API_BASE_URL",
        ),
    )
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "LLM_API_KEY", "ANTHROPIC_API_KEY", "GMI_API_KEY", "NEBIUS_API_KEY",
        ),
    )
    llm_model: str = Field(
        default="claude-sonnet-5",
        validation_alias=AliasChoices("LLM_MODEL", "GMI_MODEL", "NEBIUS_CHAT_MODEL"),
    )
    llm_max_tokens: int = Field(
        default=32000,
        validation_alias=AliasChoices("LLM_MAX_TOKENS", "GMI_MAX_TOKENS", "NEBIUS_MAX_TOKENS"),
    )

    # --- per-agent LLM overrides (fall back to LLM_* above) ---
    tutor_llm_base_url: str = Field(default="", validation_alias=AliasChoices("TUTOR_LLM_BASE_URL"))
    tutor_llm_api_key: str = Field(default="", validation_alias=AliasChoices("TUTOR_LLM_API_KEY"))
    tutor_llm_model: str = Field(default="", validation_alias=AliasChoices("TUTOR_LLM_MODEL"))
    coursegen_llm_base_url: str = Field(
        default="", validation_alias=AliasChoices("COURSEGEN_LLM_BASE_URL")
    )
    coursegen_llm_api_key: str = Field(
        default="", validation_alias=AliasChoices("COURSEGEN_LLM_API_KEY")
    )
    coursegen_llm_model: str = Field(
        default="", validation_alias=AliasChoices("COURSEGEN_LLM_MODEL")
    )
    # fast_gen Phase 7: per-stage coursegen tiers. Planning/syllabus and the grounding
    # review are small structured outputs — a fast model does them at a fraction of the
    # latency; only the capsule author needs the big model. Fallback chain:
    # COURSEGEN_<STAGE>_LLM_* -> COURSEGEN_LLM_* -> LLM_*.
    coursegen_planner_llm_base_url: str = Field(
        default="", validation_alias=AliasChoices("COURSEGEN_PLANNER_LLM_BASE_URL")
    )
    coursegen_planner_llm_api_key: str = Field(
        default="", validation_alias=AliasChoices("COURSEGEN_PLANNER_LLM_API_KEY")
    )
    coursegen_planner_llm_model: str = Field(
        default="", validation_alias=AliasChoices("COURSEGEN_PLANNER_LLM_MODEL")
    )
    coursegen_review_llm_base_url: str = Field(
        default="", validation_alias=AliasChoices("COURSEGEN_REVIEW_LLM_BASE_URL")
    )
    coursegen_review_llm_api_key: str = Field(
        default="", validation_alias=AliasChoices("COURSEGEN_REVIEW_LLM_API_KEY")
    )
    coursegen_review_llm_model: str = Field(
        default="", validation_alias=AliasChoices("COURSEGEN_REVIEW_LLM_MODEL")
    )
    insights_llm_base_url: str = Field(
        default="", validation_alias=AliasChoices("INSIGHTS_LLM_BASE_URL")
    )
    insights_llm_api_key: str = Field(
        default="", validation_alias=AliasChoices("INSIGHTS_LLM_API_KEY")
    )
    insights_llm_model: str = Field(
        default="", validation_alias=AliasChoices("INSIGHTS_LLM_MODEL")
    )
    # Surgical lesson-edit agent (Viewer section PATCH / slash insert). Separate from
    # coursegen so in-place edits preserve UI instead of re-authoring. Fallback:
    # LESSON_EDIT_LLM_* → COURSEGEN_LLM_* → LLM_*.
    lesson_edit_llm_base_url: str = Field(
        default="", validation_alias=AliasChoices("LESSON_EDIT_LLM_BASE_URL")
    )
    lesson_edit_llm_api_key: str = Field(
        default="", validation_alias=AliasChoices("LESSON_EDIT_LLM_API_KEY")
    )
    lesson_edit_llm_model: str = Field(
        default="", validation_alias=AliasChoices("LESSON_EDIT_LLM_MODEL")
    )

    # --- personal learning insights ---
    insights_enabled: bool = Field(default=True, validation_alias="INSIGHTS_ENABLED")
    insights_agent_enabled: bool = Field(
        default=True, validation_alias="INSIGHTS_AGENT_ENABLED"
    )
    insights_raw_event_retention_days: int = Field(
        default=90, validation_alias="INSIGHTS_RAW_EVENT_RETENTION_DAYS", ge=7, le=365
    )
    insights_agent_refresh_minutes: int = Field(
        default=60, validation_alias="INSIGHTS_AGENT_REFRESH_MINUTES", ge=5, le=1440
    )

    # --- OpenAI media (images + lesson TTS). Reuses OPENAI_API_KEY /
    # OPENAI_REALTIME_API_KEY when OPENAI_IMAGE_API_KEY is unset. ---
    openai_image_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_IMAGE_API_KEY", "OPENAI_API_KEY"),
    )
    openai_image_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("OPENAI_IMAGE_BASE_URL", "OPENAI_BASE_URL"),
    )
    openai_image_model: str = Field(
        default="gpt-image-1.5",
        validation_alias=AliasChoices("OPENAI_IMAGE_MODEL"),
    )
    openai_image_quality: str = Field(
        default="medium",
        validation_alias=AliasChoices("OPENAI_IMAGE_QUALITY"),
    )
    openai_tts_model: str = Field(
        default="gpt-4o-mini-tts",
        validation_alias=AliasChoices("OPENAI_TTS_MODEL"),
    )
    openai_tts_voice: str = Field(
        default="alloy",
        validation_alias=AliasChoices("OPENAI_TTS_VOICE"),
    )
    image_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices("IMAGE_PROVIDER"),
    )  # openai only (legacy tokenrouter/gmi ignored)
    image_timeout_seconds: float = Field(
        default=300.0,
        validation_alias=AliasChoices("IMAGE_TIMEOUT_SECONDS"),
        ge=30.0,
        le=900.0,
    )

    # Legacy GMI / TokenRouter fields kept as unused stubs so old .env files still load.
    gmi_api_key: str = ""
    gmi_media_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("GMI_MEDIA_BASE_URL"),
    )
    gmi_image_model: str = Field(default="", validation_alias=AliasChoices("GMI_IMAGE_MODEL"))
    gmi_tts_model: str = ""
    tokenrouter_api_key: str = Field(
        default="", validation_alias=AliasChoices("TOKENROUTER_API_KEY")
    )
    tokenrouter_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("TOKENROUTER_BASE_URL"),
    )
    tokenrouter_image_model: str = Field(
        default="",
        validation_alias=AliasChoices("TOKENROUTER_IMAGE_MODEL"),
    )

    # --- 3D mesh: Pixal3D / self-hosted Hunyuan / Tencent / GMI / Atlas ---
    pixal3d_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("PIXAL3D_BASE_URL"),
    )  # Backend-only image-to-GLB API; never expose this URL to the browser.
    pixal3d_resolution: int = Field(
        default=1536,
        validation_alias=AliasChoices("PIXAL3D_RESOLUTION"),
    )
    pixal3d_seed: int = Field(
        default=0,
        validation_alias=AliasChoices("PIXAL3D_SEED"),
    )
    pixal3d_manual_fov: float = Field(
        default=-1.0,
        validation_alias=AliasChoices("PIXAL3D_MANUAL_FOV"),
        ge=-1.0,
        le=180.0,
    )
    pixal3d_skip_preprocess: bool = Field(
        default=False,
        validation_alias=AliasChoices("PIXAL3D_SKIP_PREPROCESS"),
    )
    pixal3d_texture_size: int = Field(
        default=4096,
        validation_alias=AliasChoices("PIXAL3D_TEXTURE_SIZE"),
        ge=512,
        le=8192,
    )
    pixal3d_timeout_seconds: float = Field(
        default=900.0,
        validation_alias=AliasChoices("PIXAL3D_TIMEOUT_SECONDS"),
        ge=60.0,
        le=1800.0,
    )
    pixal3d_busy_retries: int = Field(
        default=3,
        validation_alias=AliasChoices("PIXAL3D_BUSY_RETRIES"),
        ge=0,
        le=20,
    )
    pixal3d_busy_retry_seconds: float = Field(
        default=20.0,
        validation_alias=AliasChoices("PIXAL3D_BUSY_RETRY_SECONDS"),
        ge=0.1,
        le=120.0,
    )
    mesh_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("MESH_BASE_URL"),
    )  # e.g. http://localhost:8080 — self-hosted Hunyuan3D API
    mesh_steps: int = Field(
        default=30,
        validation_alias=AliasChoices("MESH_STEPS"),
        ge=1,
        le=100,
    )
    mesh_octree_resolution: int = Field(
        default=256,
        validation_alias=AliasChoices("MESH_OCTREE_RESOLUTION"),
        ge=64,
        le=512,
    )
    tencentcloud_secret_id: str = Field(
        default="",
        validation_alias=AliasChoices("TENCENTCLOUD_SECRET_ID", "TENCENT_SECRET_ID"),
    )
    tencentcloud_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("TENCENTCLOUD_SECRET_KEY", "TENCENT_SECRET_KEY"),
    )
    tencentcloud_region: str = Field(
        default="ap-singapore",
        validation_alias=AliasChoices("TENCENTCLOUD_REGION", "TENCENT_REGION"),
    )
    tencent_hunyuan_edition: str = Field(
        default="rapid",
        validation_alias=AliasChoices("TENCENT_HUNYUAN_EDITION"),
    )  # rapid (cheaper) | pro
    atlascloud_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ATLASCLOUD_API_KEY", "ATLAS_CLOUD_API_KEY"),
    )
    atlascloud_base_url: str = Field(
        default="https://api.atlascloud.ai",
        validation_alias=AliasChoices("ATLASCLOUD_BASE_URL", "ATLAS_CLOUD_BASE_URL"),
    )
    mesh_provider: str = Field(
        default="auto",
        validation_alias=AliasChoices("MESH_PROVIDER"),
    )  # auto | pixal3d | selfhosted | tencent | gmi | atlas
    # Max Hunyuan API calls per studio chapter (rest of catalog uses procedural).
    mesh_studio_max_hunyuan: int = Field(
        default=3,
        validation_alias=AliasChoices("MESH_STUDIO_MAX_HUNYUAN"),
        ge=0,
        le=12,
    )
    # Geometry budget for each generated Studio GLB. Pixal3D supports up to one
    # million faces; individual providers apply their own lower safety clamp.
    mesh_studio_face_count: int = Field(
        default=1_000_000,
        validation_alias=AliasChoices("MESH_STUDIO_FACE_COUNT"),
        ge=1_000,
        le=1_000_000,
    )

    # --- research / web search ---
    search_provider: str = Field(
        default="youcom",
        validation_alias=AliasChoices("SEARCH_PROVIDER", "PROVIDER_SEARCH"),
    )  # exa | youcom
    exa_api_key: str = ""
    youcom_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("YOUCOM_API_KEY"),
    )

    # --- maps (free, no key) ---
    maps_provider: str = "osm"
    osm_tile_upstream: str = "https://tile.openstreetmap.org"
    nominatim_url: str = "https://nominatim.openstreetmap.org"

    # --- pipeline / infra ---
    max_gen_retries: int = Field(
        default=2,
        validation_alias=AliasChoices("MAX_GEN_RETRIES", "GENERATION_RETRY_CAP"),
    )
    runtime_validation_enabled: bool = True
    database_url: str = "sqlite:///./hituto.db"
    # LangGraph HITL checkpointer path (SQLite). Empty → derived from database_url / cwd.
    langgraph_checkpoint_path: str = Field(
        default="",
        validation_alias=AliasChoices("LANGGRAPH_CHECKPOINT_PATH"),
    )
    frontend_origin: str = "http://localhost:5173"
    tool_base: str = ""

    # --- observability (optional LangSmith; opt-in, never required at startup) ---
    langsmith_tracing: bool = Field(default=False, validation_alias=AliasChoices("LANGSMITH_TRACING"))
    langsmith_api_key: str = Field(default="", validation_alias=AliasChoices("LANGSMITH_API_KEY"))
    langsmith_project: str = Field(
        default="hituto",
        validation_alias=AliasChoices("LANGSMITH_PROJECT"),
    )

    # --- InsForge storage (durable source-document / mesh uploads) ---
    # When INSFORGE_API_KEY + INSFORGE_BASE_URL are set, uploads go to InsForge
    # Storage instead of only on local disk. Unset → local-disk fallback (offline/tests).
    insforge_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("INSFORGE_BASE_URL", "INSFORGE_URL", "OSS_HOST"),
    )
    insforge_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("INSFORGE_API_KEY", "INSFORGE_KEY"),
    )
    storage_bucket: str = Field(
        default="source-documents",
        validation_alias=AliasChoices("STORAGE_BUCKET"),
    )
    # Hunyuan GLBs — durable across local/dev and remote compute (ephemeral disk).
    mesh_storage_bucket: str = Field(
        default="meshes",
        validation_alias=AliasChoices("MESH_STORAGE_BUCKET"),
    )

    # --- Clerk auth (session JWT from @clerk/react; verified against Clerk JWKS, RS256) ---
    # Issuer is the Clerk Frontend API origin, e.g. https://<slug>.clerk.accounts.dev (dev)
    # or https://clerk.yourdomain.com (prod). JWKS is derived as {issuer}/.well-known/jwks.json
    # unless CLERK_JWKS_URL overrides it.
    clerk_jwt_issuer: str = Field(
        default="",
        validation_alias=AliasChoices("CLERK_JWT_ISSUER", "CLERK_ISSUER"),
    )
    clerk_jwks_url: str = Field(
        default="",
        validation_alias=AliasChoices("CLERK_JWKS_URL"),
    )
    # Optional: comma-separated allowed `azp` (authorized party) origins. Empty = skip azp check.
    clerk_authorized_parties: str = Field(
        default="",
        validation_alias=AliasChoices("CLERK_AUTHORIZED_PARTIES"),
    )
    auth_disabled: bool = Field(default=False, validation_alias="AUTH_DISABLED")

    # Excalidraw whiteboard viewer SPA (InsForge-hosted /public/whiteboard or local :5174).
    # Frontend also reads VITE_WHITEBOARD_VIEWER_URL; this is for server-side docs/config.
    whiteboard_viewer_url: str = Field(
        default="",
        validation_alias=AliasChoices("WHITEBOARD_VIEWER_URL"),
    )

    # --- document-grounded courses ---
    doc_grounded_enabled: bool = True
    deep_agents_enabled: bool = False
    # Chapter-outline HITL: cap on LLM revision rounds (soft — direct-edit + approve always works).
    max_outline_revisions: int = Field(
        default=5, validation_alias=AliasChoices("MAX_OUTLINE_REVISIONS")
    )
    # A2UI JSON lessons — OFF by default. Course chapters use HTML section fan-out
    # with live gen_fragment streaming (better GenerationTheater UX). Set
    # COURSEGEN_A2UI_LESSONS=1 only for experiments; page.py does not prefer A2UI.
    coursegen_a2ui_lessons: bool = Field(
        default=False,
        validation_alias=AliasChoices("COURSEGEN_A2UI_LESSONS"),
    )
    # Route Viewer targeted refine to section PATCH APIs instead of whole-doc generation.
    surgical_edit_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("SURGICAL_EDIT_ENABLED"),
    )
    # fast_gen Phase 4: skeleton SSE frame + live fragment streaming into the
    # sandboxed shell iframe while a lesson generates (specs/fast_gen §4).
    # Stream frames only reach the generating user's live session; the capsule
    # gate before persist is unchanged.
    gen_streaming_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("GEN_SKELETON_STREAMING", "GEN_STREAMING_ENABLED"),
    )
    # fast_gen Phase 2 (§2.1): run the plan LLM and best-effort web research concurrently
    # for ungrounded lessons (the search query is the lesson title, known before planning).
    gen_parallel_interpret: bool = Field(
        default=True,
        validation_alias=AliasChoices("GEN_PARALLEL_INTERPRET"),
    )
    # fast_gen Phase 3 (§2.2): mesh generation runs as a background job instead of
    # blocking the pipeline (Hunyuan polls can take minutes). Fast/cached meshes still
    # land in v1; slow ones late-join a new artifact version on studio lessons.
    gen_async_assets: bool = Field(
        default=True,
        validation_alias=AliasChoices("GEN_ASYNC_ASSETS"),
    )
    # fast_gen Phase 5 (§4.2): author page-lesson sections as parallel LLM calls streamed
    # into the shell iframe per-section; assembled document still passes the full capsule
    # gate before persist. Falls back to whole-document authoring on any failure.
    gen_section_fanout: bool = Field(
        default=True,
        validation_alias=AliasChoices("GEN_SECTION_FANOUT"),
    )
    # Concurrent section-author LLM calls per lesson.
    gen_section_concurrency: int = Field(
        default=3,
        validation_alias=AliasChoices("GEN_SECTION_CONCURRENCY"),
    )
    # fast_gen Phase 6 (§2.4): on a repair attempt, race the repair-prompted generation
    # against a fresh rewrite and let the deterministic capsule gate pick the winner.
    # Doubles token cost on retries only.
    gen_hedged_retries: bool = Field(
        default=True,
        validation_alias=AliasChoices("GEN_HEDGED_RETRIES"),
    )
    # specs/design_agents step 4: the `reading` design — document-grounded lessons render
    # the source's own prose with a validated annotation layer (objectives, margin notes,
    # comprehension checks) through a trusted renderer. No LLM-written HTML, no capsule.
    reading_design_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("READING_DESIGN_ENABLED"),
    )
    # GameManifest design: archetype=game → validated toon-gallery manifest + server
    # Three.js runtime (no LLM-authored game loop). Fail-closed to page when off / invalid.
    game_design_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("GAME_DESIGN_ENABLED"),
    )
    upload_dir: str = "uploads"
    max_upload_mb: int = 25
    video_grounded_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("VIDEO_GROUNDED_ENABLED"),
    )
    max_video_upload_mb: int = Field(
        default=250,
        validation_alias=AliasChoices("MAX_VIDEO_UPLOAD_MB"),
    )
    video_transcription_model: str = Field(
        default="nova-3",
        validation_alias=AliasChoices("VIDEO_TRANSCRIPTION_MODEL"),
    )
    video_checkpoint_timeout_s: int = Field(
        default=60,
        validation_alias=AliasChoices("VIDEO_CHECKPOINT_TIMEOUT_S"),
    )
    max_pages: int = 400
    parse_timeout_s: float = Field(
        default=120.0,
        validation_alias=AliasChoices("RAG_PARSE_TIMEOUT_S", "PARSE_TIMEOUT_S"),
    )
    # rag-context: LiteParse dual path (Phase 1). Default on for new deploys; set 0 for
    # legacy PyMuPDF-only PDF ingest. Tests leave this unset and use FakeLiteParse.
    rag_liteparse_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("RAG_LITEPARSE_ENABLED"),
    )
    # OCR for LiteParse: auto | true | false. `auto` probes is_complex; enabling OCR
    # may need Tesseract/lang packs — see docs/RELEASE.md.
    rag_ocr_enabled: str = Field(
        default="auto",
        validation_alias=AliasChoices("RAG_OCR_ENABLED"),
    )
    rag_tree_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("RAG_TREE_ENABLED"),
    )
    rag_source_unit_tokens: int = Field(
        default=1200,
        validation_alias=AliasChoices("RAG_SOURCE_UNIT_TOKENS"),
    )
    rag_lesson_context_tokens: int = Field(
        default=24000,
        validation_alias=AliasChoices("RAG_LESSON_CONTEXT_TOKENS"),
    )
    rag_tree_full_tokens: int = Field(
        default=80000,
        validation_alias=AliasChoices("RAG_TREE_FULL_TOKENS"),
    )
    # Declared context window for the teaching-map model (clamps RAG_TREE_FULL_TOKENS).
    rag_tree_context_window: int = Field(
        default=128000,
        validation_alias=AliasChoices("RAG_TREE_CONTEXT_WINDOW"),
    )
    # Reserve for system prompt + structured JSON completion.
    rag_tree_output_reserve: int = Field(
        default=8192,
        validation_alias=AliasChoices("RAG_TREE_OUTPUT_RESERVE"),
    )
    rag_ocr_min_confidence: float = Field(
        default=0.55,
        validation_alias=AliasChoices("RAG_OCR_MIN_CONFIDENCE"),
    )
    # Coursegen plans from teaching_map when present; otherwise synthesizes from sections.
    rag_teaching_map_planner: bool = Field(
        default=True,
        validation_alias=AliasChoices("RAG_TEACHING_MAP_PLANNER"),
    )
    rag_chapter_embed: bool = Field(
        default=True,
        validation_alias=AliasChoices("RAG_CHAPTER_EMBED"),
    )
    rag_answer_context_tokens: int = Field(
        default=4000,
        validation_alias=AliasChoices("RAG_ANSWER_CONTEXT_TOKENS"),
    )
    chunk_size_tokens: int = 1000
    chunk_overlap_tokens: int = 150
    max_chunks_per_source_pack: int = 10
    # Embeddings — OpenAI-compatible client (base URL + key + model).
    embedding_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices("EMBEDDING_PROVIDER", "PROVIDER_EMBEDDINGS"),
    )  # openai-compatible live client
    embedding_base_url: str = Field(
        default="https://api.tokenfactory.nebius.com/v1",
        validation_alias=AliasChoices("EMBEDDING_BASE_URL", "NEBIUS_BASE_URL"),
    )
    embedding_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("EMBEDDING_API_KEY", "NEBIUS_API_KEY", "OPENAI_API_KEY"),
    )
    embedding_model: str = Field(
        default="Qwen/Qwen3-Embedding-8B",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "NEBIUS_EMBEDDING_MODEL"),
    )
    embedding_dim: int = Field(
        default=1536,
        validation_alias=AliasChoices("EMBEDDING_DIM", "NEBIUS_EMBEDDING_DIMENSION"),
    )
    vector_store: str = "keyword"
    course_tier: str = "standard"
    small_doc_char_threshold: int = 24000
    sandbox_provider: str = "none"

    # --- voice instructor (OpenAI Realtime S2S active path) ---
    # Additive surface, OFF by default. The WebSocket endpoint closes and the frontend hides
    # the affordance unless `voice_ready()` is true. The active path is a server-to-server
    # OpenAI Realtime session; the old Deepgram cascade remains importable only for manual
    # recovery and is not an automatic fallback.
    #
    # VOICE_LLM_* below are kept for the legacy cascade and for strong generate_ui regeneration.
    # They do not gate the active OpenAI Realtime voice session.
    voice_llm_base_url: str = Field(
        default="", validation_alias=AliasChoices("VOICE_LLM_BASE_URL")
    )
    voice_llm_api_key: str = Field(
        default="", validation_alias=AliasChoices("VOICE_LLM_API_KEY")
    )
    voice_llm_model: str = Field(
        default="Qwen/Qwen3-30B-A3B-Instruct-2507",
        validation_alias=AliasChoices("VOICE_LLM_MODEL"),
    )
    # Must be generous: widget tool calls (render_ui A2UI trees, quizzes, tables) carry large
    # JSON argument payloads. At 1500 the JSON is truncated mid-object, which — for models that
    # emit tool calls inline in `content` (e.g. Qwen on Nebius/vLLM) — leaves an unparseable
    # <tool_call> blob that renders no widget and can leak raw JSON into the spoken reply.
    voice_llm_max_tokens: int = Field(
        default=4096, validation_alias=AliasChoices("VOICE_LLM_MAX_TOKENS")
    )
    # --- billing / credit metering (services/billing_service.py) -----------------
    # Allowances are resolved from the Clerk session JWT `pla` claim via
    # billing_plans.py. These env knobs only rename the free tier / override the
    # free-tier course count when the JWT has no plan (local demos).
    billing_plan_name: str = Field(
        default="Early Explorer", validation_alias=AliasChoices("BILLING_PLAN_NAME")
    )
    billing_course_credits: int = Field(
        default=1, validation_alias=AliasChoices("BILLING_COURSE_CREDITS")
    )
    # Fail-open: metering always records, but creation is only blocked at zero
    # remaining credits when this is set.
    billing_enforce: bool = Field(default=False, validation_alias=AliasChoices("BILLING_ENFORCE"))

    voice_enabled: bool = Field(default=False, validation_alias=AliasChoices("VOICE_ENABLED"))
    voice_brain: str = Field(
        default=ACTIVE_VOICE_PROVIDER,
        validation_alias=AliasChoices("VOICE_PROVIDER"),
    )
    openai_realtime_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_REALTIME_API_KEY", "OPENAI_API_KEY"),
    )
    openai_realtime_model: str = Field(
        default="gpt-realtime-2.1",
        validation_alias=AliasChoices("OPENAI_REALTIME_MODEL"),
    )
    openai_realtime_voice: str = Field(
        default="verse",
        validation_alias=AliasChoices("OPENAI_REALTIME_VOICE"),
    )
    openai_realtime_url: str = Field(
        default="wss://api.openai.com/v1/realtime",
        validation_alias=AliasChoices("OPENAI_REALTIME_URL"),
    )
    openai_realtime_transcription_model: str = Field(
        default="gpt-realtime-whisper",
        validation_alias=AliasChoices("OPENAI_REALTIME_TRANSCRIPTION_MODEL"),
    )
    # Legacy Deepgram cascade settings. Kept for manual recovery only; not used by
    # `voice_ready()` and not wired as a fallback from the active OpenAI Realtime session.
    deepgram_api_key: str = Field(default="", validation_alias=AliasChoices("DEEPGRAM_API_KEY"))
    deepgram_stt_model: str = Field(
        default="flux-general-en",
        validation_alias=AliasChoices("DEEPGRAM_STT_MODEL"),
    )
    deepgram_tts_model: str = Field(
        default="aura-2-thalia-en",
        validation_alias=AliasChoices("DEEPGRAM_TTS_MODEL"),
    )
    voice_sample_rate: int = Field(default=24000, validation_alias=AliasChoices("VOICE_SAMPLE_RATE"))
    voice_tts_sample_rate: int = Field(
        default=24000, validation_alias=AliasChoices("VOICE_TTS_SAMPLE_RATE")
    )
    voice_session_max_minutes: int = Field(
        default=15, validation_alias=AliasChoices("VOICE_SESSION_MAX_MINUTES")
    )
    voice_idle_timeout_s: int = Field(
        default=60, validation_alias=AliasChoices("VOICE_IDLE_TIMEOUT_S")
    )
    voice_page_tool_timeout_s: float = Field(
        default=8.0, validation_alias=AliasChoices("VOICE_PAGE_TOOL_TIMEOUT_S")
    )

    @field_validator("voice_brain", mode="before")
    @classmethod
    def _force_active_voice_provider(cls, _value: str) -> str:
        # There is intentionally no runtime provider switch or Deepgram fallback.
        return ACTIVE_VOICE_PROVIDER

    @field_validator("pixal3d_resolution")
    @classmethod
    def _validate_pixal3d_resolution(cls, value: int) -> int:
        if value not in (512, 1024, 1536):
            raise ValueError("PIXAL3D_RESOLUTION must be 512, 1024, or 1536")
        return value

    def resolved_voice_llm_base_url(self) -> str:
        """Voice-agent LLM endpoint, falling back to the general LLM endpoint (Nebius)."""
        return self.voice_llm_base_url or self.llm_base_url

    def resolved_voice_llm_api_key(self) -> str:
        """Voice-agent LLM key, falling back to the general LLM key."""
        return self.voice_llm_api_key or self.llm_api_key

    def resolved_voice_llm_model(self) -> str:
        """Voice-agent model, falling back to the general model if not separately configured."""
        return self.voice_llm_model or self.llm_model

    def resolved_tutor_llm_base_url(self) -> str:
        return self.tutor_llm_base_url or self.llm_base_url

    def resolved_tutor_llm_api_key(self) -> str:
        return self.tutor_llm_api_key or self.llm_api_key

    def resolved_tutor_llm_model(self) -> str:
        return self.tutor_llm_model or self.llm_model

    def resolved_coursegen_llm_base_url(self) -> str:
        return self.coursegen_llm_base_url or self.llm_base_url

    def resolved_coursegen_llm_api_key(self) -> str:
        return self.coursegen_llm_api_key or self.llm_api_key

    def resolved_coursegen_llm_model(self) -> str:
        return self.coursegen_llm_model or self.llm_model

    def resolved_coursegen_planner_llm_base_url(self) -> str:
        return self.coursegen_planner_llm_base_url or self.resolved_coursegen_llm_base_url()

    def resolved_coursegen_planner_llm_api_key(self) -> str:
        return self.coursegen_planner_llm_api_key or self.resolved_coursegen_llm_api_key()

    def resolved_coursegen_planner_llm_model(self) -> str:
        return self.coursegen_planner_llm_model or self.resolved_coursegen_llm_model()

    def resolved_coursegen_review_llm_base_url(self) -> str:
        return self.coursegen_review_llm_base_url or self.resolved_coursegen_llm_base_url()

    def resolved_coursegen_review_llm_api_key(self) -> str:
        return self.coursegen_review_llm_api_key or self.resolved_coursegen_llm_api_key()

    def resolved_coursegen_review_llm_model(self) -> str:
        return self.coursegen_review_llm_model or self.resolved_coursegen_llm_model()

    def resolved_insights_llm_base_url(self) -> str:
        return self.insights_llm_base_url or self.llm_base_url

    def resolved_insights_llm_api_key(self) -> str:
        return self.insights_llm_api_key or self.llm_api_key

    def resolved_insights_llm_model(self) -> str:
        return self.insights_llm_model or self.llm_model

    def resolved_lesson_edit_llm_base_url(self) -> str:
        return (
            self.lesson_edit_llm_base_url
            or self.resolved_coursegen_llm_base_url()
        )

    def resolved_lesson_edit_llm_api_key(self) -> str:
        return (
            self.lesson_edit_llm_api_key
            or self.resolved_coursegen_llm_api_key()
        )

    def resolved_lesson_edit_llm_model(self) -> str:
        return (
            self.lesson_edit_llm_model
            or self.resolved_coursegen_llm_model()
        )

    def voice_ready(self) -> bool:
        """True only when voice is enabled and the active realtime credential is set.

        `/health`, the WebSocket endpoint, and the frontend all gate on this. Deepgram and
        legacy VOICE_LLM_* credentials are intentionally not considered here.
        """
        return bool(self.voice_enabled and self.openai_realtime_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_database_url() -> str:
    """Resolve sqlite relative paths to an absolute file under backend/.

    InsForge / hosted Postgres ships as `postgresql://...`. SQLAlchemy 2 + the
    `psycopg` (v3) extra needs the `postgresql+psycopg://` dialect URL.
    """
    url = get_settings().database_url
    if url.startswith("sqlite:///./"):
        path = (_BACKEND_ROOT / url.removeprefix("sqlite:///./")).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    return url
