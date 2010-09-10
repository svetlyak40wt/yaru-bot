CREATE TABLE ids(
    user_id INTEGER NOT NULL,
    id INTEGER NOT NULL,
    updated_at DATETIME NOT NULL,
    url VARCHAR(255) NOT NULL,
    PRIMARY KEY (user_id, id)
);

ALTER TABLE users
    ADD last_post_at DATETIME,
    ADD last_comment_at DATETIME;

DROP TABLE post_links;

