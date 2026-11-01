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
| 24 heures | ⏳ À faire (connexion + clic sur le bouton de téléchargement) |
| Le Temps | ⏳ À faire (interception réseau) |
| Le Monde | ⏳ À faire (interception réseau) |

## Structure du projet

```text
NewsArchiver/
├── run.py                       # Point d'entrée
├── requirements.txt
├── .env.example                 # Modèle de configuration (copier en .env)
└── newsarchiver/
    ├── config.py                # Lecture de la configuration (.env)
    ├── base.py                  # Classe abstraite BaseDownloader (idempotence)
    └── sources/
        └── le_courrier.py       # Téléchargeur de Le Courrier
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

## Utilisation

```bash
python run.py              # toutes les sources
python run.py le_courrier  # une seule source
```

Pour un lancement automatique, créer une tâche planifiée du système (par exemple chaque jeudi pour Le Courrier).

## Archivage

Les PDF sont rangés par journal puis par année :

```text
ARCHIVE_PATH/Le Courrier/2026/LeCourrier_2026_41_10-29.pdf
```

Pour Le Courrier, le schéma est `LeCourrier_AAAA_NN_MM-JJ.pdf` : `NN` est le numéro de l'année (repart à 1 en janvier) et `MM-JJ` la date de parution.

- **Idempotence :** avant de lancer le navigateur, le script vérifie si le numéro du dernier jeudi est déjà archivé. Après téléchargement, il vérifie à nouveau avec le vrai numéro. Un fichier existant n'est jamais écrasé.
- **Le Courrier :** le lien du dernier numéro est lu sur la page d'accueil. Le numéro et la date de parution sont lus sur la première page du PDF (ligne « N° 41 | JEUDI 29 OCTOBRE 2026 »). Le numéro depuis la création du journal (« N° 35744 ») est ignoré, car il n'est pas fiable.
- **Numéro illisible :** le PDF est rangé dans `ARCHIVE_PATH/Le Courrier/_a-verifier/` et un avertissement est affiché. Il faut le renommer à la main.
