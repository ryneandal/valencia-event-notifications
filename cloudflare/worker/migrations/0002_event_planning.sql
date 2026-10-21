-- Public event evidence and collection checks; existing times stay unverified.
ALTER TABLE events ADD COLUMN end_at TEXT;
ALTER TABLE events ADD COLUMN time_precision TEXT NOT NULL DEFAULT 'unverified'
  CHECK (time_precision IN ('date', 'datetime', 'unverified'));
ALTER TABLE events ADD COLUMN location TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS source_checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  checked_date TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok', 'error')),
  fetched_count INTEGER NOT NULL DEFAULT 0 CHECK (fetched_count >= 0),
  event_count INTEGER NOT NULL DEFAULT 0 CHECK (event_count >= 0),
  checked_at TEXT NOT NULL,
  error_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_checks_date_time
  ON source_checks(checked_date, checked_at);
