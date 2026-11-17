#!/usr/bin/env bash
# One-command TEST deployment of School ERP on the VPS (demo data, SQLite).
# Usage (as root):  bash deploy/setup_test_vps.sh
# Result: http://<server-ip>:<public port>  — free ports are picked automatically (from 8010 / 8090)
# and remembered in /etc/school-erp.ports for re-runs.
set -euo pipefail

APP_DIR=/var/www/school-erp
REPO=https://github.com/techumwindia/School-Enterprise-Resource-Planning-Automation.
IP=$(hostname -I | awk '{print $1}')
PORTS_FILE=/etc/school-erp.ports

port_in_use() { ss -ltnH | awk '{print $4}' | grep -qE ":$1\$"; }
free_port() {           # first free port starting at $1
  local p=$1
  while port_in_use "$p"; do p=$((p + 1)); done
  echo "$p"
}

if [ -f "$PORTS_FILE" ]; then
  . "$PORTS_FILE"       # re-run: keep the ports chosen the first time
else
  APP_PORT=$(free_port 8010)                 # internal Gunicorn port
  PUBLIC_PORT=$(free_port 8090)              # port opened in the browser
  [ "$PUBLIC_PORT" = "$APP_PORT" ] && PUBLIC_PORT=$(free_port $((APP_PORT + 1)))
  printf 'APP_PORT=%s\nPUBLIC_PORT=%s\n' "$APP_PORT" "$PUBLIC_PORT" > "$PORTS_FILE"
fi
echo "==> Using internal port $APP_PORT, public port $PUBLIC_PORT"

echo "==> Installing packages"
apt-get update -qq
apt-get install -y -qq python3-venv git nginx >/dev/null

echo "==> Getting the code"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull -q
else
  git clone -q "$REPO" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> Python environment"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q "Django>=5.2,<5.3" whitenoise gunicorn python-dotenv

if [ ! -f .env ]; then
  echo "==> Writing .env (test settings)"
  cat > .env <<EOF
DJANGO_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=$IP,127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=http://$IP:$PUBLIC_PORT
DJANGO_SECURE_COOKIES=False
DB_ENGINE=sqlite
SCHOOL_NAME=Demo Matriculation Higher Secondary School
SCHOOL_ADDRESS=Main Road, Sivakasi, Tamil Nadu
SCHOOL_PHONE=+91 00000 00000
SCHOOL_EMAIL=office@school.example
EOF
fi

sed -i "s#^DJANGO_CSRF_TRUSTED_ORIGINS=.*#DJANGO_CSRF_TRUSTED_ORIGINS=http://$IP:$PUBLIC_PORT#" .env

echo "==> Database, demo data, static files"
set -a; . ./.env; set +a
venv/bin/python manage.py migrate --noinput -v0
venv/bin/python manage.py seed_demo
venv/bin/python manage.py collectstatic --noinput -v0
chown -R www-data:www-data "$APP_DIR"

echo "==> systemd service"
sed "s/127.0.0.1:8005/127.0.0.1:$APP_PORT/" deploy/school-erp.service > /etc/systemd/system/school-erp.service
systemctl daemon-reload
systemctl enable -q school-erp
systemctl restart school-erp

echo "==> Nginx"
cat > /etc/nginx/sites-available/school-erp <<EOF
server {
    listen $PUBLIC_PORT;
    server_name _;
    client_max_body_size 10M;
    location /media/ { alias $APP_DIR/media/; }
    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host:\$server_port;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sf /etc/nginx/sites-available/school-erp /etc/nginx/sites-enabled/school-erp
nginx -t -q
systemctl reload nginx

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow "$PUBLIC_PORT/tcp" >/dev/null
fi

sleep 2
code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PUBLIC_PORT/login/" || true)
echo
echo "Login page check: HTTP $code (200 = working)"
echo "Open:  http://$IP:$PUBLIC_PORT"
echo "Logins: admin/admin123  teacher1/teacher123  accountant/accounts123  student1/student123  parent1/parent123"
