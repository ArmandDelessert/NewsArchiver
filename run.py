#!/usr/bin/env python3
"""
Usage:
    python run.py                # exécute toutes les sources actives
    python run.py le_courrier    # exécute uniquement Le Courrier
"""
import sys
from playwright.sync_api import sync_playwright

from newsarchiver.config import load_config
from newsarchiver.sources.le_courrier import LeCourrierDownloader

SOURCES = {
    "le_courrier": LeCourrierDownloader,
}


def main() -> None:
    config = load_config()
    requested = sys.argv[1] if len(sys.argv) > 1 else "all"

    if requested == "all":
        to_run = list(SOURCES.values())
    elif requested in SOURCES:
        to_run = [SOURCES[requested]]
    else:
        print(f"Source inconnue : {requested!r}. Sources disponibles : {list(SOURCES)}")
        sys.exit(1)

    headless = not config.debug

    with sync_playwright() as p:
        for DownloaderClass in to_run:
            browser = p.chromium.launch(headless=headless)
            try:
                page = browser.new_page()
                downloader = DownloaderClass(config)
                downloader.run(page)
            finally:
                browser.close()


if __name__ == "__main__":
    main()
