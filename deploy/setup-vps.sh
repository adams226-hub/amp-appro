#!/usr/bin/env bash
# Installation d'AMP Appro sur un VPS Ubuntu 22.04/24.04 ou Debian 12 neuf.
# ATTENTION : NE PAS lancer sur un VPS gere par Coolify (ou tout autre proxy deja
# installe sur les ports 80/443) : Nginx entrerait en conflit et couperait les autres applis.
# Usage (en root ou via sudo, depuis le dossier amp-appro) :
#   sudo bash deploy/setup-vps.sh appro.mon-domaine.bf admin@mon-domaine.bf
# Prerequis : le DNS du domaine (enregistrement A) pointe deja vers l'IP du VPS.
set -euo pipefail

DOMAIN="${1:?Usage: setup-vps.sh <domaine> <email-certbot>}"
EMAIL="${2:?Usage: setup-vps.sh <domaine> <email-certbot>}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then echo "Lancer avec sudo." >&2; exit 1; fi

echo "== 1/6 Paquets systeme"
apt-get update
apt-get install -y ca-certificates curl nginx certbot python3-certbot-nginx ufw
if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker nginx

echo "== 2/6 Pare-feu (SSH, HTTP, HTTPS uniquement)"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
# Le port 8080 n'est publie que sur 127.0.0.1 par compose.yaml : il reste inaccessible depuis Internet.

echo "== 3/6 Configuration .env"
cd "$PROJECT_DIR"
if [[ ! -f .env ]]; then cp .env.example .env; fi
chmod 600 .env

echo "== 4/6 Construction et demarrage du conteneur"
docker compose config --quiet
docker compose build
docker compose up -d
for i in $(seq 1 20); do
    curl -fsS http://127.0.0.1:8080/health >/dev/null && break
    sleep 2
done
curl -fsS http://127.0.0.1:8080/health && echo

echo "== 5/6 Nginx + certificat HTTPS Let's Encrypt"
install -m 644 deploy/amp-appro-proxy.conf /etc/nginx/amp-appro-proxy.conf
sed "s/appro\.exemple\.bf/$DOMAIN/g" deploy/nginx-amp-appro.conf > /etc/nginx/conf.d/amp-appro.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
certbot --nginx -d "$DOMAIN" -m "$EMAIL" --agree-tos --no-eff-email --redirect --non-interactive

echo "== 6/6 Sauvegarde quotidienne (03:15 UTC)"
chmod 700 deploy/backup.sh
cat > /etc/cron.d/amp-appro-backup <<EOF
15 3 * * * root $PROJECT_DIR/deploy/backup.sh >> /var/log/amp-appro-backup.log 2>&1
EOF
chmod 644 /etc/cron.d/amp-appro-backup

echo
echo "Installation terminee. Verification publique :"
curl -fsS "https://$DOMAIN/health" && echo
echo
echo "Etape suivante (une seule fois, interactive) :"
echo "  cd $PROJECT_DIR && docker compose run --rm api --init-admin"
echo "Puis dans l'application : URL du serveur = https://$DOMAIN"
