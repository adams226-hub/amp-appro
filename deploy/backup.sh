#!/usr/bin/env bash
# Sauvegarde coherente de la base SQLite AMP Appro (API SQLite backup, compatible WAL).
# Usage : deploy/backup.sh            (depuis n'importe quel dossier)
# Variables optionnelles :
#   AMP_BACKUP_DIR   dossier des sauvegardes (defaut : <amp-appro>/backups)
#   AMP_BACKUP_KEEP  nombre de jours conserves (defaut : 14)
#   AMP_RCLONE_DEST  destination rclone hors VPS, ex. "b2:mon-bucket/amp-appro" (optionnel)
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${AMP_BACKUP_DIR:-$PROJECT_DIR/backups}"
KEEP_DAYS="${AMP_BACKUP_KEEP:-14}"
NAME="amp-appro-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"

cd "$PROJECT_DIR"
umask 077
mkdir -p "$BACKUP_DIR"

# 1. Copie coherente dans le tmpfs du conteneur, avec controle d'integrite
docker compose exec -T api python -c '
import os, sqlite3
src = sqlite3.connect(os.environ["AMP_DB"])
dst = sqlite3.connect("/tmp/amp-backup.sqlite3")
src.backup(dst)
ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
dst.close(); src.close()
if ok != "ok":
    raise SystemExit("integrity_check: " + ok)
'

# 2. Recuperation sur le VPS puis nettoyage du conteneur
docker compose cp api:/tmp/amp-backup.sqlite3 "$BACKUP_DIR/$NAME"
docker compose exec -T api python -c 'from pathlib import Path; Path("/tmp/amp-backup.sqlite3").unlink()'
gzip -9 "$BACKUP_DIR/$NAME"
chmod 600 "$BACKUP_DIR/$NAME.gz"

# 3. Copie hors VPS (fortement recommandee : une sauvegarde locale ne protege pas contre la perte du VPS)
if [[ -n "${AMP_RCLONE_DEST:-}" ]]; then
    rclone copy "$BACKUP_DIR/$NAME.gz" "$AMP_RCLONE_DEST"
fi

# 4. Rotation locale
find "$BACKUP_DIR" -name 'amp-appro-*.sqlite3.gz' -type f -mtime +"$KEEP_DAYS" -delete

echo "Sauvegarde OK : $BACKUP_DIR/$NAME.gz"
