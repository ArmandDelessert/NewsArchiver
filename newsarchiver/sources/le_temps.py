from datetime import date
from pathlib import Path
from playwright.sync_api import Page, Playwright

from newsarchiver.base import BaseDownloader
from newsarchiver.dates import last_issue_date_without_sunday, parse_french_date


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
        pdf = response.body()
        if pdf[:5] != b"%PDF-":
            raise RuntimeError(f"{self.source_name} : le fichier reçu n'est pas un PDF.")

        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + ".part")
        partial.write_bytes(pdf)
        partial.replace(dest)
        return dest
