from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from playwright.sync_api import Browser, BrowserContext, Page, Playwright

_VIEWPORT = {"width": 1920, "height": 1080}


class BaseDownloader(ABC):

    # Nom du fichier de session (cookies) ; None si la source est en accès libre.
    session_name: str | None = None

    # False : source en cours de développement, exclue de « python run.py » sans argument.
    ready: bool = True

    def __init__(self, config) -> None:
        self.config = config

    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    def already_archived(self) -> bool:
        """Vérification rapide, faite avant de lancer le navigateur."""

    @abstractmethod
    def download(self, page: Page) -> Path | None:
        """Télécharge et enregistre le fichier ; retourne None si rien de nouveau."""

    @property
    def session_path(self) -> Path | None:
        if self.session_name is None:
            return None
        return self.config.browser_state_dir / f"{self.session_name}.json"

    def login(self, playwright: Playwright) -> None:
        raise NotImplementedError(f"{self.source_name} n'a pas de connexion.")

    def backfill(self, playwright: Playwright, since: date | None, until: date | None) -> int:
        """Télécharge les anciens numéros ; retourne le nombre d'échecs."""
        raise NotImplementedError(f"{self.source_name} : pas de rattrapage.")

    @staticmethod
    def write_pdf(dest: Path, content: bytes) -> None:
        """Écrit le PDF via un fichier .part ; refuse un contenu qui n'est pas un PDF."""
        if content[:5] != b"%PDF-":
            raise RuntimeError("le fichier reçu n'est pas un PDF.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + ".part")
        partial.write_bytes(content)
        partial.replace(dest)

    def open_context(self, playwright: Playwright) -> tuple[Browser, BrowserContext]:
        context_args: dict = {"accept_downloads": True, "viewport": _VIEWPORT}
        if self.session_path is not None:
            if not self.session_path.exists():
                raise RuntimeError(
                    f"{self.source_name} : aucune session enregistrée. "
                    f"Lancer d'abord : python run.py login {self.session_name}"
                )
            context_args["storage_state"] = str(self.session_path)

        browser = playwright.chromium.launch(headless=not self.config.debug)
        return browser, browser.new_context(**context_args)

    def run(self, playwright: Playwright) -> None:
        if self.already_archived():
            print(f"[{self.source_name}] Déjà téléchargé — ignoré.")
            return

        browser, context = self.open_context(playwright)
        try:
            saved = self.download(context.new_page())
        finally:
            browser.close()
        if saved:
            print(f"[{self.source_name}] Enregistré : {saved}")
