from datetime import date
from pathlib import Path
from playwright.sync_api import Page

from newsarchiver.base import BaseDownloader


class LeCourrierDownloader(BaseDownloader):

    source_name = "Le Courrier"
    _SELECTOR = "#block-54 > figure > figure > a"
    _BASE_URL = "https://www.le-courrier.ch/"

    def get_target_path(self) -> Path:
        today = date.today()
        folder = self.config.archive_path / "Le Courrier" / str(today.year)
        return folder / f"LeCourrier_{today.strftime('%Y-%m-%d')}.pdf"

    def download(self, page: Page) -> Path:
        dest = self.get_target_path()

        page.goto(self._BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        el = page.wait_for_selector(self._SELECTOR, timeout=10_000)
        href = el.get_attribute("href")
        if not href:
            raise RuntimeError("Le Courrier : lien PDF introuvable sur la page d'accueil.")

        if href.startswith("/"):
            href = "https://www.le-courrier.ch" + href

        response = page.request.get(href, timeout=60_000)
        if not response.ok:
            raise RuntimeError(
                f"Le Courrier : échec du téléchargement (HTTP {response.status})."
            )

        dest.write_bytes(response.body())
        return dest
