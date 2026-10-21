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
