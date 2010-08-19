ALTER TABLE users ADD refresh_token CHAR(32) AFTER auth_token;
ALTER TABLE users MODIFY auth_token CHAR(32);


