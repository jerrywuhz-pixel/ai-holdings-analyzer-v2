-- Register Futu OpenD as the preferred real-time portfolio quote source.

INSERT INTO public.data_source_health (
  source_name,
  display_name,
  status,
  priority_cn,
  priority_hk,
  priority_us,
  config
)
VALUES (
  'futu',
  'Futu OpenD',
  'unknown',
  1,
  1,
  1,
  '{"realtime": true, "batch_size": 200, "requires": ["futu-api", "Futu OpenD"]}'::jsonb
)
ON CONFLICT (source_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  priority_cn = EXCLUDED.priority_cn,
  priority_hk = EXCLUDED.priority_hk,
  priority_us = EXCLUDED.priority_us,
  config = EXCLUDED.config,
  updated_at = now();
