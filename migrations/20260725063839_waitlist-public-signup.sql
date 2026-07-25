-- Public waitlist signup for the landing page (anon SDK insert).

CREATE TABLE public.waitlist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.waitlist ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.waitlist FROM anon, authenticated;
GRANT INSERT ON public.waitlist TO anon, authenticated;

CREATE POLICY "anon_authenticated_insert_waitlist"
  ON public.waitlist
  FOR INSERT
  TO anon, authenticated
  WITH CHECK (
    email IS NOT NULL
    AND length(trim(email)) > 3
    AND position('@' IN email) > 1
  );
