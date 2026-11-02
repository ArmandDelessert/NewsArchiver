import re
import time
from datetime import date
from pathlib import Path
from playwright.sync_api import Page, Playwright

from newsarchiver.base import BaseDownloader
from newsarchiver.dates import last_issue_date_without_sunday, month_windows, parse_french_date

_PAUSE_SECONDS = 2
_LAST_PAGE_RE = re.compile(r"[?&]page=(\d+)")


class LeTempsDownloader(BaseDownloader):

    source_name = "Le Temps"
    session_name = "letemps"
    _BASE_URL = "https://www.letemps.ch"
    _LIST_URL = f"{_BASE_URL}/pdf?publication=TPS"
    _EDITION_CARD = ".lt-card-print-edition"
    # Lien « PDF » (réservé aux abonnés connectés), à ne pas confondre avec « ePaper ».
    _PDF_LINK = "a[href^='/pdf/']:not([href$='/redirect'])"

    def _path_for(self, publication_date: date) -> Path:
        folder = self.config.archive_path / "Le Temps" / str(publication_date.year)
        return folder / f"LeTemps_{publication_date.isoformat()}.pdf"

    def already_archived(self) -> bool:
        return self._path_for(last_issue_date_without_sunday()).exists()

    def login(self, playwright: Playwright) -> None:
        # La connexion reste manuelle : aucun mot de passe n'est stocké.
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            context.new_page().goto(f"{self._BASE_URL}/compte/connexion")
            print(
                f"[{self.source_name}] Connecte-toi dans la fenêtre du navigateur "
                "(coche « Se souvenir de moi »), puis reviens ici."
            )
            input("Appuie sur Entrée une fois connecté… ")
            context.storage_state(path=str(self.session_path))
        finally:
            browser.close()
        print(f"[{self.source_name}] Session enregistrée : {self.session_path}")

    def _latest_edition(self, page: Page) -> tuple[date, str]:
        """Dernière édition de la liste : date de parution et URL du PDF."""
        page.goto(self._LIST_URL, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_selector(self._EDITION_CARD, timeout=15_000)
        cards = page.locator(self._EDITION_CARD).all()
        for card in cards:
            link = card.locator(self._PDF_LINK).first
            if link.count() == 0:
                continue
            publication_date = parse_french_date(card.inner_text())
            if publication_date:
                return publication_date, self._BASE_URL + link.get_attribute("href")
        raise RuntimeError(
            f"{self.source_name} : aucun lien PDF trouvé, session expirée ? "
            f"Relancer : python run.py login {self.session_name}"
        )

    def download(self, page: Page) -> Path | None:
        publication_date, pdf_url = self._latest_edition(page)
        dest = self._path_for(publication_date)
        if dest.exists():
            print(
                f"[{self.source_name}] La dernière édition ({dest.name}) est déjà "
                "archivée, la nouvelle n'est peut-être pas encore en ligne."
            )
            return None

        response = page.request.get(pdf_url, timeout=180_000)
        if not response.ok:
            raise RuntimeError(
                f"{self.source_name} : échec du téléchargement (HTTP {response.status})."
            )
        self.write_pdf(dest, response.body())
        return dest

    def _month_editions(self, page: Page, first: date, last: date) -> list[tuple[date, str]]:
        """Éditions d'une fenêtre de dates (la liste est paginée par 24, plafonnée à 5 pages)."""
        base = f"{self._BASE_URL}/pdf?publication=TPS&published_from={first}&published_to={last}"
        editions: list[tuple[date, str]] = []
        last_page = 1
        number = 1
        while number <= last_page:
            page.goto(f"{base}&page={number}", wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(1_000)
            if number == 1:
                for href in page.locator("a", has_text="Dernière page").evaluate_all(
                    "els => els.map(e => e.getAttribute('href'))"
                ):
                    match = _LAST_PAGE_RE.search(href or "")
                    last_page = int(match.group(1)) if match else 1
            for card in page.locator(self._EDITION_CARD).all():
                link = card.locator(self._PDF_LINK).first
                publication_date = parse_french_date(card.inner_text())
                if link.count() and publication_date:
                    editions.append((publication_date, self._BASE_URL + link.get_attribute("href")))
            number += 1
        return editions

    def backfill(self, playwright: Playwright, since: date | None, until: date | None) -> int:
        if since is None:
            raise RuntimeError("Le Temps : préciser --depuis AAAA-MM-JJ (archive depuis 2009).")
        until = until or date.today()
        browser, context = self.open_context(playwright)
        page = context.new_page()
        saved = skipped = failures = 0
        try:
            for first, last in month_windows(since, until):
                editions = self._month_editions(page, first, last)
                if not editions and not saved and not skipped:
                    print(f"[{self.source_name}] Rien pour {first:%Y-%m} (session expirée ?).")
                for publication_date, pdf_url in sorted(editions, reverse=True):
                    dest = self._path_for(publication_date)
                    if dest.exists():
                        skipped += 1
                        continue
                    try:
                        response = page.request.get(pdf_url, timeout=300_000)
                        if not response.ok:
                            raise RuntimeError(f"HTTP {response.status}")
                        self.write_pdf(dest, response.body())
                        saved += 1
                        print(f"[{self.source_name}] {dest.name} ({dest.stat().st_size // 1_000_000} Mo)")
                    except Exception as e:
                        failures += 1
                        print(f"[{self.source_name}] ÉCHEC {publication_date} : {e}")
                    time.sleep(_PAUSE_SECONDS)
        finally:
            browser.close()
        print(f"[{self.source_name}] Rattrapage terminé : {saved} enregistrés, {skipped} déjà présents, {failures} échecs.")
        return failures
