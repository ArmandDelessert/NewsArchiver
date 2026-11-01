import re
import time
from datetime import date
from io import BytesIO
from pathlib import Path
from playwright.sync_api import Page, Playwright
from pypdf import PdfReader, PdfWriter

from newsarchiver.base import BaseDownloader
from newsarchiver.dates import last_issue_date_without_sunday

_PACKAGE_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
_WAIT_SECONDS = 60


class LeMondeDownloader(BaseDownloader):
    """Le lecteur (Twipe) n'a pas de bouton « tout télécharger » : on récupère les PDF
    de chaque page avec les URL signées que le serveur fournit à la session
    connectée, puis on les assemble."""

    source_name = "Le Monde"
    session_name = "lemonde"
    _READER_URL = "https://journal.lemonde.fr/"

    def _path_for(self, publication_date: date) -> Path:
        folder = self.config.archive_path / "Le Monde" / str(publication_date.year)
        return folder / f"LeMonde_{publication_date.isoformat()}.pdf"

    def already_archived(self) -> bool:
        return self._path_for(last_issue_date_without_sunday()).exists()

    def login(self, playwright: Playwright) -> None:
        # La connexion reste manuelle : aucun mot de passe n'est stocké.
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            context.new_page().goto(self._READER_URL)
            print(
                f"[{self.source_name}] Connecte-toi dans la fenêtre du navigateur "
                "(« Se connecter » en haut), puis reviens ici."
            )
            input("Appuie sur Entrée une fois connecté… ")
            # indexed_db : le lecteur Twipe peut y garder son jeton.
            context.storage_state(path=str(self.session_path), indexed_db=True)
        finally:
            browser.close()
        print(f"[{self.source_name}] Session enregistrée : {self.session_path}")

    def _open_latest_edition(self, page: Page) -> dict:
        """Ouvre la dernière édition et retourne les données que le lecteur reçoit."""
        responses = []
        page.on("response", lambda response: responses.append(response))
        page.goto(self._READER_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3_000)
        try:  # bandeau cookies : refuser
            page.get_by_text("Continuer sans accepter").first.click(timeout=3_000)
        except Exception:
            pass
        page.locator(".main-button", has_text="Lire").first.click(timeout=15_000)

        wanted = {
            "info": "GetContentPackageInfo",
            "credentials": "GetDownloadCredentials",
            "pages": "GetPublicationPages-",
        }
        found: dict = {}
        deadline = time.monotonic() + _WAIT_SECONDS
        while len(found) < len(wanted) and time.monotonic() < deadline:
            if "secure.lemonde.fr" in page.url:
                raise RuntimeError(
                    f"{self.source_name} : session expirée. "
                    f"Relancer : python run.py login {self.session_name}"
                )
            for response in list(responses):
                for key, fragment in wanted.items():
                    if key not in found and fragment in response.url and response.ok:
                        found[key] = response.json()
            page.wait_for_timeout(500)
        missing = set(wanted) - set(found)
        if missing:
            raise RuntimeError(f"{self.source_name} : données du lecteur manquantes : {sorted(missing)}")
        return found

    def _publication_date(self, info: dict) -> date:
        # « Le Monde - 02-11-2026 »
        match = _PACKAGE_DATE_RE.search(info.get("ContentPackageName", ""))
        if not match:
            raise RuntimeError(f"{self.source_name} : date introuvable dans {info.get('ContentPackageName')!r}")
        day, month, year = map(int, match.groups())
        return date(year, month, day)

    def download(self, page: Page) -> Path | None:
        data = self._open_latest_edition(page)
        publication_date = self._publication_date(data["info"])
        dest = self._path_for(publication_date)
        if dest.exists():
            print(
                f"[{self.source_name}] La dernière édition ({dest.name}) est déjà "
                "archivée, la nouvelle n'est peut-être pas encore en ligne."
            )
            return None

        pdf_pattern = data["credentials"]["PdfPattern"]
        pages = sorted(data["pages"]["Page"], key=lambda p: p["PageNumber"])
        writer = PdfWriter()
        for entry in pages:
            url = pdf_pattern.replace("%PUBPAGE_ID%", str(entry["PublicationPageID"]))
            response = page.request.get(url, timeout=120_000)
            body = response.body() if response.ok else b""
            if body[:5] != b"%PDF-":
                raise RuntimeError(
                    f"{self.source_name} : page {entry['PageNumber']} non téléchargée "
                    f"(HTTP {response.status})."
                )
            writer.append(PdfReader(BytesIO(body)))

        if len(writer.pages) < len(pages):
            raise RuntimeError(
                f"{self.source_name} : {len(writer.pages)} pages assemblées sur {len(pages)}."
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + ".part")
        with partial.open("wb") as f:
            writer.write(f)
        partial.replace(dest)
        return dest
