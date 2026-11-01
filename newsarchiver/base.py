from abc import ABC, abstractmethod
from pathlib import Path
from playwright.sync_api import Page


class BaseDownloader(ABC):

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

    def run(self, page: Page) -> None:
        if self.already_archived():
            print(f"[{self.source_name}] Déjà téléchargé — ignoré.")
            return
        saved = self.download(page)
        if saved:
            print(f"[{self.source_name}] Enregistré : {saved}")
