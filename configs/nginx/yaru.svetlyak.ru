server {
    listen 80;
    server_name yaru.svetlyak.ru;
    location / {
        proxy_pass http://127.0.0.1:8081;
    }
    access_log /home/art/log/nginx/yaru.svetlyak-access.log timed_log;
}

