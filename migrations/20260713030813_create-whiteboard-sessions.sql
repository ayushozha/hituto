CREATE TABLE public.whiteboard_sessions (
  id VARCHAR PRIMARY KEY,
  course_id VARCHAR NOT NULL REFERENCES public.courses(id) ON DELETE CASCADE,
  lesson_id VARCHAR NOT NULL REFERENCES public.lessons(id) ON DELETE CASCADE,
  user_id VARCHAR NOT NULL,
  tool_call_id VARCHAR NOT NULL UNIQUE,
  title VARCHAR NOT NULL DEFAULT 'Whiteboard',
  intent TEXT NOT NULL DEFAULT '',
  scene JSONB NOT NULL DEFAULT '{"elements":[]}'::jsonb,
  revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX whiteboard_sessions_lesson_user_updated_idx
  ON public.whiteboard_sessions (lesson_id, user_id, updated_at DESC);

ALTER TABLE public.whiteboard_sessions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.whiteboard_sessions FROM anon, authenticated;
