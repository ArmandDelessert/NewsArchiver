# News Archiver

Automatisation de l'archivage de journaux.

## Sources à archiver

Le script automatise la récupération et l'archivage des titres suivants :

| Journal | Type | Fréquence | URL Source | Accès |
| :--- | :--- | :--- | :--- | :--- |
| **[Le Courrier](https://www.le-courrier.ch/)** | Hebdomadaire | Les jeudis | [le-courrier.ch](https://www.le-courrier.ch/) | Accès libre |
| **[24 heures](https://www.24heures.ch/)** | Quotidien | Tous les jours | [epaper.24heures.ch](https://epaper.24heures.ch/) | Abonnement requis |
| **[Le Temps](https://www.letemps.ch/)** | Quotidien | Tous les jours | [letemps.ch](https://www.letemps.ch/pdf) | Abonnement requis |
| **[Le Monde](https://www.lemonde.fr/)** | Quotidien | Tous les jours | [journal.lemonde.fr](https://journal.lemonde.fr/) | Abonnement requis |

## Stack technique

* **Moteur d'automatisation :** Playwright (navigateur Chromium en mode *Headless*)
* **Planification :** Tâches planifiées (OS local)

## État d'avancement

| Journal | Statut |
| :--- | :--- |
| Le Courrier | ✅ Implémenté |
| 24 heures | 🧪 Implémenté, à valider avec une vraie session (voir « Connexion à 24 heures ») |
| Le Temps | ✅ Implémenté (testé, téléchargement direct) |
| Le Monde | ⏳ À faire (interception réseau) |

## Structure du projet

```text
NewsArchiver/
├── run.py                       # Point d'entrée
├── requirements.txt
├── .env.example                 # Modèle de configuration (copier en .env)
└── newsarchiver/
    ├── config.py                # Lecture de la configuration (.env)
    ├── dates.py                 # Dates en français, dernière édition attendue
    ├── base.py                  # Classe abstraite BaseDownloader (idempotence, session)
    └── sources/
        ├── le_courrier.py       # Téléchargeur de Le Courrier
        ├── vingt_quatre_heures.py  # Téléchargeur de 24 heures
        └── le_temps.py          # Téléchargeur de Le Temps
```

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
copy .env.example .env   # puis adapter ARCHIVE_PATH
```

## Configuration

Les paramètres sont lus dans le fichier `.env` (exclu de Git) :

| Variable | Obligatoire | Description |
| :--- | :--- | :--- |
| `ARCHIVE_PATH` | Oui | Dossier racine de l'archivage |
| `DEBUG` | Non | `true` pour afficher le navigateur (débogage) |
| `BROWSER_STATE_DIR` | Non | Dossier des sessions de connexion (défaut : `.browser_state/`, exclu de Git) |

## Utilisation

```bash
python run.py              # toutes les sources
python run.py le_courrier  # une seule source
python run.py login 24heures  # connexion manuelle, une seule fois (idem : login letemps)
```

Pour un lancement automatique, créer une tâche planifiée du système (par exemple chaque jeudi pour Le Courrier).

## Connexion à 24 heures

La connexion passe par le SSO Tamedia (e-mail et mot de passe) protégé par Cloudflare Turnstile : elle n'est **pas automatisée**, et aucun mot de passe n'est stocké. On se connecte une fois à la main :

```bash
python run.py login 24heures
```

Un navigateur visible s'ouvre. Après connexion, appuyer sur Entrée dans le terminal : la session (cookies) est enregistrée dans `.browser_state/24heures.json`. Les exécutions suivantes réutilisent cette session en mode headless. Quand elle expire, le script affiche « session expirée » : relancer la commande ci-dessus.

## Le Temps

Connecté, la liste `letemps.ch/pdf?publication=TPS` propose un lien **PDF** direct pour chaque édition, y compris celle du lendemain, publiée la veille au soir. Le script lit la date de parution sur la carte de la dernière édition et télécharge ce PDF avec la session enregistrée (`python run.py login letemps`, connexion manuelle). Sans session valide, la liste n'affiche que des liens ePaper : le script signale alors « session expirée ».

## Archivage

Les PDF sont rangés par journal puis par année :

```text
ARCHIVE_PATH/Le Courrier/2026/LeCourrier_2026_41_10-29.pdf
ARCHIVE_PATH/24 heures/2026/24heures_2026-10-31.pdf
ARCHIVE_PATH/Le Temps/2026/LeTemps_2026-10-31.pdf
```

Pour Le Courrier, le schéma est `LeCourrier_AAAA_NN_MM-JJ.pdf` : `NN` est le numéro de l'année (repart à 1 en janvier) et `MM-JJ` la date de parution.

- **Idempotence :** avant de lancer le navigateur, le script vérifie si le numéro du dernier jeudi est déjà archivé. Après téléchargement, il vérifie à nouveau avec le vrai numéro. Un fichier existant n'est jamais écrasé.
- **Le Courrier :** le lien du dernier numéro est lu sur la page d'accueil. Le numéro et la date de parution sont lus sur la première page du PDF (ligne « N° 41 | JEUDI 29 OCTOBRE 2026 »). Le numéro depuis la création du journal (« N° 35744 ») est ignoré, car il n'est pas fiable.
- **24 heures :** la date de parution est lue dans l'URL du lecteur. Pas de parution le dimanche : la dernière édition attendue est celle du samedi. Le fichier est d'abord écrit en `.part` puis renommé après contrôle de l'en-tête `%PDF`.
- **Numéro illisible (Le Courrier) :** le PDF est rangé dans `ARCHIVE_PATH/Le Courrier/_a-verifier/` et un avertissement est affiché. Il faut le renommer à la main.
