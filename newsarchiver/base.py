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
    def get_target_path(self) -> Path: ...

    @abstractmethod
    def download(self, page: Page) -> Path: ...

    def run(self, page: Page) -> None:
        target = self.get_target_path()
        if target.exists():
            print(f"[{self.source_name}] Déjà téléchargé : {target.name} — ignoré.")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        saved = self.download(page)
        print(f"[{self.source_name}] Enregistré : {saved}")
