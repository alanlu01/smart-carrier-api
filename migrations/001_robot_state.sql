-- Apply after the existing locations/tasks migration in Supabase SQL Editor.
ALTER TABLE public.locations ADD COLUMN IF NOT EXISTS floor TEXT;
ALTER TABLE public.locations ADD COLUMN IF NOT EXISTS x DOUBLE PRECISION;
ALTER TABLE public.locations ADD COLUMN IF NOT EXISTS y DOUBLE PRECISION;
ALTER TABLE public.locations ADD COLUMN IF NOT EXISTS yaw DOUBLE PRECISION;

CREATE TABLE IF NOT EXISTS public.robots (
  id TEXT PRIMARY KEY,
  mode TEXT NOT NULL DEFAULT 'idle',
  battery DOUBLE PRECISION,
  location_code TEXT REFERENCES public.locations(code) ON DELETE SET NULL,
  x DOUBLE PRECISION,
  y DOUBLE PRECISION,
  yaw DOUBLE PRECISION,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.power_slots (
  robot_id TEXT NOT NULL REFERENCES public.robots(id) ON DELETE CASCADE,
  slot_number INTEGER NOT NULL CHECK (slot_number BETWEEN 1 AND 3),
  bank_id TEXT,
  status TEXT NOT NULL DEFAULT 'empty',
  current DOUBLE PRECISION,
  charge DOUBLE PRECISION,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (robot_id, slot_number)
);

CREATE TABLE IF NOT EXISTS public.robot_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  robot_id TEXT NOT NULL REFERENCES public.robots(id) ON DELETE CASCADE,
  task_id UUID REFERENCES public.tasks(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS robot_events_robot_created_idx
  ON public.robot_events(robot_id, created_at DESC);

ALTER TABLE public.robots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.power_slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.robot_events ENABLE ROW LEVEL SECURITY;

-- Browser users only receive read access. FastAPI uses service_role for writes.
GRANT SELECT ON public.robots, public.power_slots TO anon, authenticated;
GRANT ALL ON public.robots, public.power_slots, public.robot_events TO service_role;

DROP POLICY IF EXISTS "public read robots" ON public.robots;
CREATE POLICY "public read robots" ON public.robots FOR SELECT USING (true);
DROP POLICY IF EXISTS "public read power slots" ON public.power_slots;
CREATE POLICY "public read power slots" ON public.power_slots FOR SELECT USING (true);
