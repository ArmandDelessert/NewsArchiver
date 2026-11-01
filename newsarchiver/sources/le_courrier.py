import re
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from playwright.sync_api import Page
from pypdf import PdfReader

from newsarchiver.base import BaseDownloader
from newsarchiver.dates import MOIS

# Ligne d'en-tête de la une : « … | N° 41 | JEUDI 29 OCTOBRE 2026 | … ».
# Ancrée sur le « | » pour ne pas confondre avec « N° 9 – 2026 » (communes).
_ISSUE_RE = re.compile(
    r"N°\s*(\d{1,3})\s*\|\s*"
    r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+"
    r"(\d{1,2})\s*(?:er)?\s+([a-zéûè]+)\s+(\d{4})",
    re.IGNORECASE,
)
_JEUDI = 3
_QUARANTAINE = "_a-verifier"


class LeCourrierDownloader(BaseDownloader):

    source_name = "Le Courrier"
    _SELECTOR = "#block-54 > figure > figure > a"
    _BASE_URL = "https://www.le-courrier.ch/"

    @property
    def _root(self) -> Path:
        return self.config.archive_path / "Le Courrier"

    def _path_for(self, number: int, publication_date: date) -> Path:
        year = publication_date.year
        name = f"LeCourrier_{year}_{number:02d}_{publication_date:%m-%d}.pdf"
        return self._root / str(year) / name

    @staticmethod
    def _last_thursday() -> date:
        today = date.today()
        return today - timedelta(days=(today.weekday() - _JEUDI) % 7)

    def already_archived(self) -> bool:
        # Le numéro n'est connu qu'après téléchargement : on cherche par date.
        thursday = self._last_thursday()
        folder = self._root / str(thursday.year)
        pattern = f"LeCourrier_{thursday.year}_*_{thursday:%m-%d}.pdf"
        return any(folder.glob(pattern))

    @staticmethod
    def _read_issue(pdf: bytes) -> tuple[int, date] | None:
        text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
        for number, day, month, year in _ISSUE_RE.findall(text):
            if month.lower() in MOIS:
                return int(number), date(int(year), MOIS[month.lower()], int(day))
        return None

    def _quarantine(self, pdf: bytes) -> Path | None:
        folder = self._root / _QUARANTAINE
        folder.mkdir(parents=True, exist_ok=True)
        if any(f.read_bytes() == pdf for f in folder.glob("*.pdf")):
            print(f"[{self.source_name}] Numéro non identifiable, déjà dans {_QUARANTAINE}.")
            return None
        dest = folder / f"LeCourrier_{date.today().isoformat()}.pdf"
        n = 2
        while dest.exists():
            dest = folder / f"LeCourrier_{date.today().isoformat()}_{n}.pdf"
            n += 1
        dest.write_bytes(pdf)
        print(
            f"[{self.source_name}] ATTENTION : numéro et date illisibles dans le PDF. "
            f"Fichier à renommer à la main : {dest}"
        )
        return dest

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

        issue = self._read_issue(pdf)
        if issue is None:
            return self._quarantine(pdf)

        dest = self._path_for(*issue)
        if dest.exists():
            print(
                f"[{self.source_name}] Le dernier numéro ({dest.name}) est déjà "
                "archivé, le nouveau n'est peut-être pas encore en ligne."
            )
            return None

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(pdf)
        return dest
