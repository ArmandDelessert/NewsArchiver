#!/usr/bin/env python3
"""
Usage:
    python run.py                  # exécute toutes les sources actives
    python run.py le_courrier      # exécute une seule source
    python run.py login 24heures   # connexion manuelle (une fois), enregistre la session
    python run.py backfill letemps --depuis 2009-02-01 [--jusqu AAAA-MM-JJ]   # anciens numéros
"""
import argparse
import os
import sys
from datetime import date
from playwright.sync_api import sync_playwright

from newsarchiver import monitoring
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


def heartbeat_url(requested: str) -> str:
    """URL de ping Healthchecks.io : HEARTBEAT_URL_<SOURCE> pour une source seule (ex. HEARTBEAT_URL_LE_COURRIER),
    sinon HEARTBEAT_URL. Vide = supervision désactivée."""
    specific = os.environ.get(f"HEARTBEAT_URL_{requested.upper()}", "") if requested != "all" else ""
    return specific or os.environ.get("HEARTBEAT_URL", "")


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

    if args[:1] == ["backfill"]:
        parser = argparse.ArgumentParser(prog="run.py backfill", description="Télécharge les anciens numéros.")
        parser.add_argument("source", choices=list(SOURCES))
        parser.add_argument("--depuis", type=date.fromisoformat, metavar="AAAA-MM-JJ")
        parser.add_argument("--jusqu", type=date.fromisoformat, metavar="AAAA-MM-JJ")
        options = parser.parse_args(args[1:])
        try:
            with sync_playwright() as p:
                failures = SOURCES[options.source](config).backfill(p, options.depuis, options.jusqu)
        except (RuntimeError, NotImplementedError) as e:
            sys.exit(f"ERREUR : {e}")
        sys.exit(1 if failures else 0)

    requested = args[0] if args else "all"
    if requested == "all":
        keys = [k for k, c in SOURCES.items() if c.ready]
    elif requested in SOURCES:
        keys = [requested]
    else:
        sys.exit(f"Source inconnue : {requested!r}. Sources disponibles : {list(SOURCES)}")

    url = heartbeat_url(requested)
    monitoring.ping(url, "start")
    errors: list[str] = []
    with sync_playwright() as p:
        for key in keys:
            downloader = SOURCES[key](config)
            try:
                downloader.run(p)
            except Exception as e:  # une source en échec ne bloque pas les autres
                errors.append(f"[{downloader.source_name}] ERREUR : {e}")
                print(errors[-1], file=sys.stderr)
    monitoring.ping(url, "fail" if errors else "ok", "\n".join(errors))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
