CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  preferences_blob TEXT,
  is_active INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS magic_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  token_hash TEXT UNIQUE NOT NULL,
  purpose TEXT NOT NULL CHECK (purpose IN ('register', 'login')),
  expires_at TEXT NOT NULL,
  consumed_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  token_hash TEXT UNIQUE NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
  user_id INTEGER PRIMARY KEY,
  is_subscribed INTEGER NOT NULL DEFAULT 1 CHECK (is_subscribed IN (0, 1)),
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_key TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  start_at TEXT NOT NULL,
  end_at TEXT,
  time_precision TEXT NOT NULL DEFAULT 'unverified'
    CHECK (time_precision IN ('date', 'datetime', 'unverified')),
  location TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS digest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  digest_date TEXT UNIQUE NOT NULL,
  scheduled_for TEXT,
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running', 'completed', 'partial', 'failed')),
  event_count INTEGER NOT NULL DEFAULT 0,
  subscriber_count INTEGER NOT NULL DEFAULT 0,
  sent_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS recommendations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  digest_run_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  event_id INTEGER NOT NULL,
  position INTEGER NOT NULL CHECK (position > 0),
  relevance_reason TEXT NOT NULL,
  model_id TEXT NOT NULL,
  used_fallback INTEGER NOT NULL DEFAULT 0 CHECK (used_fallback IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (digest_run_id, user_id, event_id),
  UNIQUE (digest_run_id, user_id, position),
  FOREIGN KEY (digest_run_id) REFERENCES digest_runs(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  digest_run_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'sent', 'failed')),
  attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count > 0),
  provider_message_id TEXT,
  last_error_code TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sent_at TEXT,
  UNIQUE (digest_run_id, user_id),
  FOREIGN KEY (digest_run_id) REFERENCES digest_runs(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_magic_links_token_hash ON magic_links(token_hash);
CREATE INDEX IF NOT EXISTS idx_magic_links_user_id ON magic_links(user_id);
CREATE INDEX IF NOT EXISTS idx_events_start_at ON events(start_at);
CREATE INDEX IF NOT EXISTS idx_events_last_seen_at ON events(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_digest_runs_status ON digest_runs(status);
CREATE INDEX IF NOT EXISTS idx_recommendations_run_user
  ON recommendations(digest_run_id, user_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries(status);

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

CREATE TABLE IF NOT EXISTS delivery_preferences (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  days TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS saved_events (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_id INTEGER NOT NULL REFERENCES events(id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, event_id)
);
CREATE TABLE IF NOT EXISTS pilot_participants (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  study_code TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pilot_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  study_code TEXT NOT NULL REFERENCES pilot_participants(study_code) ON DELETE CASCADE,
  preview_date TEXT NOT NULL,
  result_state TEXT NOT NULL CHECK (result_state IN
    ('recommendations','empty','filtered','partial','unavailable')),
  useful INTEGER CHECK (useful IN (0,1)),
  action TEXT CHECK (action IN ('organizer','save','copy','calendar')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pilot_feedback_study ON pilot_feedback(study_code);
CREATE INDEX IF NOT EXISTS idx_pilot_expiry ON pilot_participants(expires_at);

CREATE TABLE IF NOT EXISTS billing_accounts (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  livemode INTEGER NOT NULL CHECK (livemode IN (0,1)),
  customer_id TEXT NOT NULL UNIQUE,
  subscription_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'none',
  cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
  current_period_end INTEGER NOT NULL DEFAULT 0,
  last_event_created INTEGER NOT NULL DEFAULT 0,
  sync_version INTEGER NOT NULL DEFAULT 0,
  checkout_key TEXT NOT NULL DEFAULT '',
  checkout_created_at INTEGER NOT NULL DEFAULT 0,
  checkout_url TEXT NOT NULL DEFAULT '',
  checkout_session_id TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (user_id, livemode)
);
