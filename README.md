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

Les PDF sont rangés par journal puis par année, et nommés avec la **date de parution** :

```text
ARCHIVE_PATH/Le Courrier/2026/LeCourrier_2026-10-29.pdf
```

- **Idempotence :** si le fichier attendu existe déjà, le script ne lance pas le navigateur.
- **Le Courrier :** le lien du dernier numéro est lu sur la page d'accueil. La date de parution est lue sur la première page du PDF (ligne « JEUDI 29 OCTOBRE 2026 »). Si elle est illisible, le script utilise la date du dernier jeudi et affiche un avertissement.
