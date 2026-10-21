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

-- Account identity is kept out of the feedback records.
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
