import re
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import Page, Playwright, TimeoutError as PlaywrightTimeout

from newsarchiver.base import BaseDownloader

_DIMANCHE = 6
# Date de l'édition affichée, dans l'URL : /read/124/124/2026-10-31/1
_URL_DATE_RE = re.compile(r"/read/\d+/\d+/(\d{4})-(\d{2})-(\d{2})/")


class VingtQuatreHeuresDownloader(BaseDownloader):

    source_name = "24 heures"
    session_name = "24heures"
    _BASE_URL = "https://epaper.24heures.ch/"
    _MENU = "div.fup-menu-item-download"
    _LOGIN_LINK = "span.fup-s-menu-login-sso"
    _DOWNLOAD_EDITION = (
        "body > div.fup-viewport > div.fup-menu > div.fup-menu-desktop > "
        "div.fup-menu-sizing-wrapper > div.fup-s-menu-container.fup-menu-container > "
        "div > div.fup-menu-item.fup-menu-item-download > div > "
        "div.fup-menu-subitem.fup-s-menu-download-edition > span"
    )

    def _path_for(self, publication_date: date) -> Path:
        folder = self.config.archive_path / "24 heures" / str(publication_date.year)
        return folder / f"24heures_{publication_date.isoformat()}.pdf"

    @staticmethod
    def _expected_date() -> date:
        # Pas de parution le dimanche : la dernière édition est celle du samedi.
        today = date.today()
        return today - timedelta(days=1) if today.weekday() == _DIMANCHE else today

    def already_archived(self) -> bool:
        return self._path_for(self._expected_date()).exists()

    def login(self, playwright: Playwright) -> None:
        # La connexion (SSO Tamedia + Cloudflare Turnstile) reste manuelle.
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            context.new_page().goto(self._BASE_URL)
            print(
                f"[{self.source_name}] Connecte-toi dans la fenêtre du navigateur "
                "(« Se connecter » en haut à gauche), puis reviens ici."
            )
            input("Appuie sur Entrée une fois connecté… ")
            context.storage_state(path=str(self.session_path))
        finally:
            browser.close()
        print(f"[{self.source_name}] Session enregistrée : {self.session_path}")

    def download(self, page: Page) -> Path | None:
        page.goto(self._BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector(self._MENU, timeout=30_000)
        page.wait_for_timeout(3_000)  # laisse le lecteur afficher l'état de connexion

        if page.locator(self._LOGIN_LINK).first.is_visible():
            raise RuntimeError(
                f"{self.source_name} : session expirée. "
                f"Relancer : python run.py login {self.session_name}"
            )

        match = _URL_DATE_RE.search(page.url)
        if not match:
            raise RuntimeError(f"{self.source_name} : date introuvable dans {page.url}")
        dest = self._path_for(date(*map(int, match.groups())))
        if dest.exists():
            print(
                f"[{self.source_name}] La dernière édition ({dest.name}) est déjà "
                "archivée, la nouvelle n'est peut-être pas encore en ligne."
            )
            return None

        # Le menu « Télécharger » s'ouvre au survol (un clic le referme).
        page.locator("div.fup-menu-desktop").get_by_text("Télécharger", exact=True).hover()
        edition = page.locator(self._DOWNLOAD_EDITION)
        edition.wait_for(state="visible", timeout=5_000)
        try:
            with page.expect_download(timeout=180_000) as download:
                edition.click()
        except PlaywrightTimeout:
            raise RuntimeError(
                f"{self.source_name} : aucun téléchargement déclenché "
                "(session expirée ou sélecteur modifié)."
            ) from None

        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + ".part")
        download.value.save_as(partial)
        if partial.read_bytes()[:5] != b"%PDF-":
            partial.unlink()
            raise RuntimeError(f"{self.source_name} : le fichier reçu n'est pas un PDF.")
        partial.replace(dest)
        return dest
