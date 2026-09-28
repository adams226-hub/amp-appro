# Mise à jour serveur du 24 septembre 2026 — .env et Docker

Destinataire : Rombat, administration informatique.
L'APK existant reste compatible. Aucun serveur n'a été déployé par cette mise à jour.

## Emplacement de AMP_DB

Dans `server/server.py`, au début du fichier :

```python
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / '.env', override=False)
DB = os.environ.get('AMP_DB', 'amp-appro.sqlite3')
HOST = os.environ.get('AMP_HOST', '127.0.0.1')
PORT = int(os.environ.get('AMP_PORT', '8080'))
```

La fonction `connect()` utilise ensuite `sqlite3.connect(DB, timeout=15)`.
`AMP_DB` désigne un CHEMIN de fichier SQLite, pas une URL PostgreSQL. Ne pas y mettre de chaîne `postgresql://`.
Le `.env` est recherché à la racine `amp-appro/`, au même niveau que `compose.yaml`, quel que soit le répertoire courant du shell. Les variables déjà définies dans l'environnement sont prioritaires (`override=False`). Un AMP_DB relatif reste relatif au répertoire de lancement, pour préserver le comportement du pilote initial ; utiliser un chemin absolu lors du déploiement. Le dossier parent doit exister et être accessible en écriture.

`python-dotenv==1.2.1` est déclaré dans `requirements.txt`. Aucun secret n'est fourni dans l'archive.

## Installation Docker sur un VPS Linux

Prérequis : Docker Engine et plugin Docker Compose fonctionnels, accès au registre d'images/PyPI, domaine et reverse proxy HTTPS gérés par l'informaticien. Depuis le dossier décompressé `amp-appro` :

```bash
cp .env.example .env
chmod 600 .env
docker compose config --quiet
docker compose build
docker compose run --rm api --init-admin
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8080/health
```

La création du premier administrateur est interactive, à effectuer une seule fois sur une base neuve. Saisir votre propre email et mot de passe ; ne pas les placer dans le Dockerfile ou la ligne de commande. Si un administrateur existe déjà dans une base migrée, sa création n'est pas nécessaire.

Le `.env` pour Docker contient `AMP_DB=/data/amp-appro.sqlite3`. Compose lit ce fichier avec `env_file` et injecte les variables dans le processus. Il n'est pas copié dans l'image. Le chargement python-dotenv est utile notamment lors d'un lancement hors Docker.

Compose impose une écoute `0.0.0.0:8080` à l'intérieur du conteneur afin que la redirection de port fonctionne. Sur le VPS, seul `127.0.0.1:8080` est publié. Le service n'est donc pas exposé directement sur l'interface publique. Les variables HOST/PORT du `.env` servent au lancement hors Docker ; les surcharges Compose sont intentionnelles.

Le processus fonctionne sous UID/GID 10001, sans privilège root ; le système de fichiers de l'image est en lecture seule. SQLite et ses fichiers WAL/SHM restent dans le volume Docker `amp_data`, monté en `/data`. La création initiale du volume Docker reprend les droits du répertoire /data de l'image. Ne pas supprimer le volume et ne pas exécuter `docker compose down -v` : cette commande supprimerait les données.

Conserver le même nom de projet Compose `amp-appro-pilot` et le même volume lors des mises à jour. Ne pas multiplier les réplicas de ce pilote SQLite.

## HTTPS et accès APK

Configurer Nginx sur le VPS pour transmettre le domaine choisi vers `http://127.0.0.1:8080`. Le README principal fournit un exemple. Installer un certificat HTTPS valide, limiter les requêtes et les tentatives de connexion au niveau du reverse proxy, puis tester `/health` depuis le domaine public. Le conteneur n'obtient pas automatiquement un domaine ni un certificat.

Dans l'APK : renseigner l'URL HTTPS du domaine, l'email du compte créé et son mot de passe. Pas de recompilation Android nécessaire. Garder une URL sans sous-chemin pour le montage décrit ici.

## Mise à jour d'une installation existante

Sauvegarder la base existante avant tout changement. L'archive n'inclut aucune base et la création du volume ne migre pas automatiquement une ancienne base. Pour transférer une base existante, arrêter l'ancien service puis la sauvegarder avec l'API SQLite backup (ou faire intervenir l'administrateur SQLite). Copier la sauvegarde cohérente dans le volume, sous le nom défini par AMP_DB, avec propriétaire 10001:10001 avant de démarrer. Ne jamais copier seulement le fichier principal d'une base active en mode WAL.

Pour les mises à jour de code après installation :

```bash
docker compose up -d --build
docker compose ps
```

Le volume est conservé. Vérifier le résultat fonctionnel après mise à jour.

## Exemple de sauvegarde cohérente

Le conteneur doit être démarré. La commande produit une sauvegarde par l'API SQLite, puis la récupère sur le VPS. Le nom unique évite d'écraser une ancienne sauvegarde.

```bash
mkdir -p backups
backup_name="amp-appro-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
docker compose exec -T api python -c 'import os,sqlite3; source=sqlite3.connect(os.environ["AMP_DB"]); target=sqlite3.connect("/tmp/amp-backup.sqlite3"); source.backup(target); target.close(); source.close()'
docker compose cp api:/tmp/amp-backup.sqlite3 "backups/$backup_name"
chmod 600 "backups/$backup_name"
docker compose exec -T api python -c 'from pathlib import Path; Path("/tmp/amp-backup.sqlite3").unlink()'
```

Planifier une copie chiffrée hors VPS et un test de restauration. La sauvegarde dans le même VPS ne protège pas contre sa perte. Le volume persistant n'est pas une sauvegarde.

## Sans Docker

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Modifier AMP_DB pour indiquer un chemin absolu local et accessible en écriture (pas /data sauf si ce dossier a été préparé). Laisser AMP_HOST=127.0.0.1. Puis :

```bash
python server/server.py --init-admin
python server/server.py
```

Le fichier .env est chargé automatiquement. `--host` et `--port` permettent de surcharger explicitement l'écoute. L'installation doit rester derrière HTTPS.

## Vérifications et limites

Les tests Python du workflow et les tests de configuration .env doivent passer avec :

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Cette mise à jour ne transforme pas le pilote en version de production complète. Le serveur utilise encore `http.server`, SQLite et les fonctions métier du pilote ; un déploiement définitif nécessite le durcissement et les compléments du README. Le conteneur ne remplace ni le contrôle des droits métier, ni l'antivirus des pièces, ni les sauvegardes, ni les fonctions manquantes.

Validation effectuée dans l'environnement de création : tests de configuration, tests métier et démarrage HTTP local. Docker Engine n'étant pas disponible, l'image n'a pas été construite ni le conteneur démarré ici. Rombat doit exécuter build, init-admin, up, contrôle santé, vérification de persistance et tests APK sur le VPS avant utilisation.

Références : https://pypi.org/project/python-dotenv/ ; https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/ ; https://docs.docker.com/compose/gettingstarted/
