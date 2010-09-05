CREATE TABLE stats(
    `date` DATE NOT NULL PRIMARY KEY,
    new_users INTEGER NOT NULL DEFAULT 0,
    unsubscribed INTEGER NOT NULL DEFAULT 0,
    posts_processed INTEGER NOT NULL DEFAULT 0,
    posts_failed INTEGER NOT NULL DEFAULT 0,
    sent_posts INTEGER NOT NULL DEFAULT 0,
    sent_links INTEGER NOT NULL DEFAULT 0
);
