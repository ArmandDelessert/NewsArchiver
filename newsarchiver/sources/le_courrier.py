import re
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from playwright.sync_api import Page
from pypdf import PdfReader

from newsarchiver.base import BaseDownloader

_MOIS = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12,
}
_DATE_RE = re.compile(
    r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+"
    r"(\d{1,2})(?:er)?\s+([a-zéûè]+)\s+(\d{4})",
    re.IGNORECASE,
)
_JEUDI = 3


class LeCourrierDownloader(BaseDownloader):

    source_name = "Le Courrier"
    _SELECTOR = "#block-54 > figure > figure > a"
    _BASE_URL = "https://www.le-courrier.ch/"

    def _path_for(self, publication_date: date) -> Path:
        folder = self.config.archive_path / "Le Courrier" / str(publication_date.year)
        return folder / f"LeCourrier_{publication_date.isoformat()}.pdf"

    @staticmethod
    def _last_thursday() -> date:
        today = date.today()
        return today - timedelta(days=(today.weekday() - _JEUDI) % 7)

    def get_target_path(self) -> Path:
        return self._path_for(self._last_thursday())

    @staticmethod
    def _read_publication_date(pdf: bytes) -> date | None:
        text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
        for jour, mois, annee in _DATE_RE.findall(text):
            if mois.lower() in _MOIS:
                return date(int(annee), _MOIS[mois.lower()], int(jour))
        return None

    def download(self, page: Page) -> Path | None:
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
        pdf = response.body()

        publication_date = self._read_publication_date(pdf)
        if publication_date is None:
            publication_date = self._last_thursday()
            print(
                f"[{self.source_name}] Date de parution illisible dans le PDF, "
                f"repli sur le dernier jeudi ({publication_date})."
            )

        dest = self._path_for(publication_date)
        if dest.exists():
            print(
                f"[{self.source_name}] Le dernier numéro ({dest.name}) est déjà "
                "archivé, le nouveau n'est peut-être pas encore en ligne."
            )
            return None

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(pdf)
        return dest
