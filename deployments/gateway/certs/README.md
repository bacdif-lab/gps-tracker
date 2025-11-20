Coloca aquí los certificados TLS de desarrollo (local.crt y local.key) para que Nginx exponga HTTPS.
Para generar uno auto-firmado: `openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout local.key -out local.crt -subj "/CN=localhost"`.
