-- Forward-only: apply before deploying the Jev-enabled Worker.
CREATE TABLE IF NOT EXISTS jev_answer_cache (
  cache_key TEXT NOT NULL,
  question_id TEXT NOT NULL,
  model TEXT NOT NULL,
  p_yes REAL NOT NULL CHECK (p_yes >= 0 AND p_yes <= 1),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (cache_key, question_id)
);

CREATE TABLE IF NOT EXISTS jev_evaluations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  digest_run_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  event_id INTEGER NOT NULL,
  selected_event_types TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  question_version TEXT NOT NULL,
  scoring_version TEXT NOT NULL,
  model TEXT,
  components TEXT NOT NULL,
  threshold REAL NOT NULL CHECK (threshold >= 0 AND threshold <= 1),
  irrelevance_score REAL CHECK (irrelevance_score >= 0 AND irrelevance_score <= 1),
  decision TEXT NOT NULL CHECK (decision IN ('eligible', 'irrelevant', 'unknown')),
  status TEXT NOT NULL CHECK (status IN ('evaluated', 'uncertain', 'fallback')),
  error_code TEXT,
  evaluated_at TEXT NOT NULL,
  FOREIGN KEY (digest_run_id) REFERENCES digest_runs(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (event_id) REFERENCES events(id)
);

CREATE INDEX IF NOT EXISTS idx_jev_evaluations_run_user
  ON jev_evaluations(digest_run_id, user_id);
CREATE INDEX IF NOT EXISTS idx_jev_evaluations_event
  ON jev_evaluations(event_id);
CREATE INDEX IF NOT EXISTS idx_jev_answer_cache_created
  ON jev_answer_cache(created_at);
