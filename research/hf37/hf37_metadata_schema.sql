-- HF37 MNP metadata schema: store hashes and locations, never full trade tape.
-- Apply using a privileged migration role, not the read-only analysis connector.
CREATE TABLE IF NOT EXISTS hf37_tape_window (
  universe_sha256 char(64) NOT NULL,
  feed text NOT NULL CHECK (feed IN ('iex')),
  symbol varchar(12) NOT NULL,
  kind text NOT NULL CHECK (kind IN ('trades','quotes')),
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL,
  manifest_sha256 char(64) NOT NULL,
  page_count integer NOT NULL CHECK (page_count >= 1),
  record_count bigint NOT NULL CHECK (record_count >= 0),
  object_uri text NOT NULL,
  verified_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL CHECK (status IN ('VERIFIED','QUARANTINED')),
  PRIMARY KEY (universe_sha256,feed,symbol,kind,window_start,window_end),
  CHECK (window_start < window_end),
  CHECK (window_end - window_start <= interval '5 minutes'),
  CHECK (length(object_uri)>0)
);
CREATE INDEX IF NOT EXISTS hf37_tape_window_status_idx
  ON hf37_tape_window(status,window_start,symbol);
-- A VERIFIED row means source bytes have been independently checked against
-- SHA256 and persisted at object_uri. Never mark VERIFIED for ephemeral files.
