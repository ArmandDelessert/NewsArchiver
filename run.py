#!/usr/bin/env python3
"""
Usage:
    python run.py                  # exécute toutes les sources actives
    python run.py le_courrier      # exécute une seule source
    python run.py login 24heures   # connexion manuelle (une fois), enregistre la session
"""
import sys
from playwright.sync_api import sync_playwright

from newsarchiver.config import load_config
from newsarchiver.sources.le_courrier import LeCourrierDownloader
from newsarchiver.sources.le_monde import LeMondeDownloader
from newsarchiver.sources.le_temps import LeTempsDownloader
from newsarchiver.sources.vingt_quatre_heures import VingtQuatreHeuresDownloader

SOURCES = {
    "le_courrier": LeCourrierDownloader,
    "24heures": VingtQuatreHeuresDownloader,
    "letemps": LeTempsDownloader,
    "lemonde": LeMondeDownloader,
}


def main() -> None:
    config = load_config()
    args = sys.argv[1:]

    if args[:1] == ["login"]:
        key = args[1] if len(args) > 1 else None
        cls = SOURCES.get(key)
        if cls is None or cls.session_name is None:
            sys.exit(f"Usage : python run.py login <source>. "
                     f"Sources avec connexion : {[k for k, c in SOURCES.items() if c.session_name]}")
        with sync_playwright() as p:
            cls(config).login(p)
        return

    requested = args[0] if args else "all"
    if requested == "all":
        keys = [k for k, c in SOURCES.items() if c.ready]
    elif requested in SOURCES:
        keys = [requested]
    else:
        sys.exit(f"Source inconnue : {requested!r}. Sources disponibles : {list(SOURCES)}")

    failed = False
    with sync_playwright() as p:
        for key in keys:
            downloader = SOURCES[key](config)
            try:
                downloader.run(p)
            except Exception as e:  # une source en échec ne bloque pas les autres
                failed = True
                print(f"[{downloader.source_name}] ERREUR : {e}", file=sys.stderr)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
