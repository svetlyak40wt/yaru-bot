ALTER TABLE users ADD next_poll_at DATETIME NOT NULL;
UPDATE users SET next_poll_at = UTC_TIMESTAMP();
