# AMP Appro — application Android pilote 0.1

**Mise à jour serveur du 24/09/2026 : prise en charge automatique de .env et fichiers Docker. Lire [DEPLOIEMENT_DOCKER.md](DEPLOIEMENT_DOCKER.md) pour la procédure recommandée. L’APK est inchangé.**

## Installer et essayer

1. Copier `AMP_Appro_Pilote.apk` sur un téléphone Android 8.0 ou supérieur.
2. Ouvrir le fichier. Si Android le demande, autoriser temporairement l'installation depuis l'application utilisée pour ouvrir le fichier. Ne pas désactiver Play Protect.
3. Ouvrir AMP Appro, puis « Essayer la démonstration ».
4. Une demande fictive est déjà présente. Dans Réglages, choisir successivement Achats, Comptabilité et DG pour tester le circuit.
5. Après approbation, revenir au profil Achats pour enregistrer la transmission au fournisseur, puis au profil Demandeur pour réceptionner.
6. Depuis un dossier, « Imprimer / Enregistrer en PDF » ouvre l'impression Android. Choisir « Enregistrer au format PDF ».

La démonstration reste sur le téléphone. Elle ne transmet ni email ni ordre d'achat. Le sélecteur de rôle n'existe pas en mode entreprise. Les données sont conservées après fermeture ; une désinstallation les efface. La signature de cet APK est un certificat de pilote, pas la signature officielle de l'entreprise.

## Fonctions incluses

- Interface française adaptée au téléphone, tableau de bord, recherche, filtres et historique.
- Demandes multilignes de fournitures ou prestations, urgence, date et lieu de besoin.
- Brouillon local manuel, puis soumission en ligne. Pas de soumission automatique après retour du réseau.
- Chiffrage par ligne, fournisseur, devis, prix, TVA, conditions de paiement.
- Pré-visa comptable avec imputation textuelle et réservation du budget chantier.
- Approbation DG horodatée, retours aux Achats et rejets motivés.
- Confirmation de transmission de commande, réception partielle, BL/PV référencé, clôture.
- Pièces PDF, JPEG et PNG ajoutées avant contrôle comptable ; téléchargement des pièces via le sélecteur Android.
- Historique d'activité dans l'application, actualisation manuelle et toutes les 30 secondes sur Accueil/Activité en mode connecté.
- Création de comptes et de chantiers/services par l'administrateur en mode connecté.
- API centrale et tests fournis dans `server/` et `tests/`.

## Ce qui n'est pas encore livré

Ce pilote n'est pas l'ensemble de la version de production décrite dans le cahier des charges initial. Il ne comprend pas : serveur hébergé, configuration des vrais comptes AMP, récupération de mot de passe, MFA/SSO, désactivation des utilisateurs depuis l'interface, rôles multiples/délégations, périmètres de chantier des services centraux, annulation/avenants après commande, catalogue administrable, stock, fournisseur normalisé, comptabilité externe, email/push Android, génération PDF automatique côté serveur, signature par certificat, antivirus des pièces et politique d'archivage inviolable. Les réceptions stockent les quantités acceptées et une référence BL/PV ; le téléversement d'un BL/PV après commande et le suivi structuré des refus sont à compléter.

Tous les demandeurs voient les chantiers disponibles mais seulement leurs propres dossiers. Achats, Comptabilité, DG et Administrateur voient les dossiers de l'entreprise. L'Administrateur ne peut pas donner de visa financier. Un utilisateur a un rôle unique dans ce pilote. Le retour est aux Achats, qui peuvent réviser le chiffrage. Une modification du besoin demande un rejet motivé et une nouvelle demande.

Les montants sont arrondis à l'unité XOF par ligne, HT puis TVA. Les budgets sont des enveloppes globales par chantier/service, sans exercice ni ventilation par poste dans le pilote. Le disponible ignore tout engagement réalisé hors application. Une commande clôturée reste engagée ; aucune écriture de paiement n'est gérée.

## Serveur central à installer

L'APK seul ne crée pas de serveur. Fournir un nom de domaine HTTPS et un hébergement avant utilisation partagée. Le code serveur du pilote utilise SQLite transactionnel (avec python-dotenv pour la configuration), pas encore le schéma PostgreSQL du document d'architecture. La migration PostgreSQL, les périmètres par chantier et les fonctions listées ci-dessus doivent être terminés avant généralisation.

Python 3.11 ou supérieur. Depuis le dossier `server` :

```bash
python3 -m pip install -r ../requirements.txt
export AMP_DB=/chemin/protege/amp-appro.sqlite3
python3 server.py --init-admin
python3 server.py --port 8080
```

La première commande demande l'identité du premier administrateur et son mot de passe sans l'afficher. Aucun identifiant par défaut n'est fourni. Hors Docker, le serveur écoute par défaut sur 127.0.0.1. AMP_HOST et AMP_PORT sont configurables ; Compose impose une écoute interne sur 0.0.0.0 et publie le port uniquement sur 127.0.0.1 du VPS. Placer un reverse proxy HTTPS devant celui-ci et lancer le serveur sous un utilisateur système dédié, sans privilège root. Ne pas exposer directement le serveur HTTP Python sur Internet.

Exemple de reverse proxy Nginx à adapter par l'administrateur :

```nginx
server {
    listen 443 ssl;
    server_name appro.votre-entreprise.bf;
    ssl_certificate /chemin/fullchain.pem;
    ssl_certificate_key /chemin/privkey.pem;
    client_max_body_size 8m;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Prévoir certificat valide, sauvegardes avec restauration testée, stockage chiffré, limitation de débit au proxy et examen de sécurité. Les pièces sont dans SQLite dans ce pilote, pas dans un stockage objet. La session expire après 8 heures et le jeton reste seulement en mémoire de l'application. Un brouillon local peut contenir des informations chantier : utiliser uniquement des téléphones professionnels protégés. Le mot de passe initial des utilisateurs est créé par l'administrateur et doit être transmis par un canal approprié ; le changement de mot de passe utilisateur reste à développer.

Dans AMP Appro, renseigner l'URL HTTPS du serveur, puis le compte administrateur. Créer les chantiers et les comptes. Les autres téléphones utilisent la même URL. Les données réelles du serveur ne sont pas copiées dans les données de démonstration.

## Vérifications

```bash
python3 -m unittest discover -s tests -v
```

Le test DOM `tests/dom.cjs` (jsdom) a également vérifié la création, le chiffrage, le pré-visa, l'approbation, la réception partielle et la persistance locale. Il ne remplace pas un test visuel Android.

Les tests couvrent le circuit complet, la réception partielle et le dépassement, les rôles, les versions périmées, les réservations budgétaires et l'accès aux pièces. Le test `tests/ui.cjs` utilise Playwright (à installer séparément) pour parcourir l'interface de démonstration.

L'APK est compilé avec Android SDK 35 et signé avec les schémas APK v2/v3. Le fichier a été vérifié par apksigner. Le navigateur de test n'a pas pu être exécuté dans cet environnement ; la vérification visuelle reste à faire. Aucune installation sur téléphone physique ou émulateur Android n'a été réalisée dans l'environnement de création. Tester l'installation, le clavier, le sélecteur de fichiers et l'impression PDF sur les téléphones utilisés par l'entreprise.

## Recompiler

Le projet natif Java n'utilise pas de bibliothèque tierce. Il encapsule l'interface locale dans une WebView, bloque la navigation externe et n'autorise pas le HTTP non chiffré. Les API Android démarrent à la version 26.

Installer un JDK 17, Android SDK platform 35 et build-tools 35.0.0, puis adapter `build.sh`. Il accepte aussi ECJ si javac n'est pas disponible. Pour les mises à jour du pilote, conserver le certificat de pilote inclus et augmenter versionCode dans le manifeste. Pour production, créer une nouvelle clé protégée et un identifiant de package approprié ; ne pas employer la clé publique de développement incluse ici.

Sources de référence Android :
- https://developer.android.com/build/building-cmdline
- https://developer.android.com/tools/apksigner
