CREATE TABLE post_links(url VARCHAR(255) NOT NULL PRIMARY KEY, hash CHAR(10) NOT NULL, user_id INTEGER NOT NULL, created_at DATETIME NOT NULL);

CREATE UNIQUE INDEX by_user_and_hash ON post_links(user_id, hash);
