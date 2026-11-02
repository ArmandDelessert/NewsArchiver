import re
import time
from collections.abc import Callable
from datetime import date
from io import BytesIO
from pathlib import Path
from playwright.sync_api import Page, Playwright
from pypdf import PdfReader, PdfWriter

from newsarchiver.base import BaseDownloader
from newsarchiver.dates import last_issue_date_without_sunday

_PACKAGE_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
_WAIT_SECONDS = 60
_PAUSE_SECONDS = 2


class LeMondeDownloader(BaseDownloader):
    """Deux sources de PDF, selon l'âge de l'édition :

    - 30 derniers jours : le lecteur (Twipe) n'a pas de bouton « tout télécharger ».
      On récupère le PDF de chaque page avec les URL signées que le serveur fournit
      à la session connectée, puis on les assemble.
    - de 1 à 3 mois : page d'archives, un PDF complet par édition.
    """

    source_name = "Le Monde"
    session_name = "lemonde"
    _READER_URL = "https://journal.lemonde.fr/"
    _ARCHIVE_URL = "https://macommande.lemonde.fr/archives"

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

    def _collect(self, page: Page, trigger: Callable[[], None], wanted: dict[str, str]) -> dict:
        """Lance `trigger`, puis attend les réponses réseau du lecteur contenant ces fragments d'URL."""
        responses = []
        listener = lambda response: responses.append(response)
        page.on("response", listener)
        try:
            trigger()
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
        finally:
            page.remove_listener("response", listener)
        missing = set(wanted) - set(found)
        if missing:
            raise RuntimeError(f"{self.source_name} : données du lecteur manquantes : {sorted(missing)}")
        return found

    _EDITION_DATA = {
        "info": "GetContentPackageInfo",
        "credentials": "GetDownloadCredentials",
        "pages": "GetPublicationPages-",
    }

    def _open_latest_edition(self, page: Page) -> dict:
        def trigger() -> None:
            page.goto(self._READER_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3_000)
            try:  # bandeau cookies : refuser
                page.get_by_text("Continuer sans accepter").first.click(timeout=3_000)
            except Exception:
                pass
            page.locator(".main-button", has_text="Lire").first.click(timeout=15_000)

        return self._collect(page, trigger, self._EDITION_DATA)

    def _open_edition(self, page: Page, package_id: int) -> dict:
        url = (
            f"{self._READER_URL}data/{package_id}/reader/reader.html"
            f"?t={int(time.time() * 1000)}#!{package_id}"
        )
        return self._collect(
            page, lambda: page.goto(url, wait_until="domcontentloaded", timeout=60_000), self._EDITION_DATA
        )

    def _publication_date(self, info: dict) -> date:
        # « Le Monde - 02-11-2026 »
        match = _PACKAGE_DATE_RE.search(info.get("ContentPackageName", ""))
        if not match:
            raise RuntimeError(f"{self.source_name} : date introuvable dans {info.get('ContentPackageName')!r}")
        day, month, year = map(int, match.groups())
        return date(year, month, day)

    def _assemble(self, page: Page, data: dict, dest: Path) -> None:
        """Télécharge le PDF de chaque page de l'édition et les assemble dans `dest`."""
        pdf_pattern = data["credentials"]["PdfPattern"]
        pages = sorted(data["pages"]["Page"], key=lambda p: p["PageNumber"])
        writer = PdfWriter()
        for entry in pages:
            url = pdf_pattern.replace("%PUBPAGE_ID%", str(entry["PublicationPageID"]))
            response = page.request.get(url, timeout=120_000)
            body = response.body() if response.ok else b""
            if body[:5] != b"%PDF-":
                raise RuntimeError(f"page {entry['PageNumber']} non téléchargée (HTTP {response.status}).")
            writer.append(PdfReader(BytesIO(body)))

        if len(writer.pages) < len(pages):
            raise RuntimeError(f"{len(writer.pages)} pages assemblées sur {len(pages)}.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + ".part")
        with partial.open("wb") as f:
            writer.write(f)
        partial.replace(dest)

    def download(self, page: Page) -> Path | None:
        data = self._open_latest_edition(page)
        dest = self._path_for(self._publication_date(data["info"]))
        if dest.exists():
            print(
                f"[{self.source_name}] La dernière édition ({dest.name}) est déjà "
                "archivée, la nouvelle n'est peut-être pas encore en ligne."
            )
            return None
        self._assemble(page, data, dest)
        return dest

    @staticmethod
    def _in_range(day: date, since: date | None, until: date | None) -> bool:
        return (since is None or day >= since) and (until is None or day <= until)

    def _backfill_kiosk(self, page: Page, since: date | None, until: date | None) -> tuple[int, int]:
        """Éditions du kiosque (30 derniers jours) : retourne (enregistrées, échecs)."""
        lists = self._collect(
            page,
            lambda: page.goto(self._READER_URL, wait_until="domcontentloaded", timeout=60_000),
            {"list": "getcontentpackagelist/TWPLMOLMO"},
        )
        saved = failures = 0
        for package in lists["list"]:
            day = date.fromisoformat(package["PublicationDate"][:10])
            dest = self._path_for(day)
            if not self._in_range(day, since, until) or dest.exists():
                continue
            try:
                data = self._open_edition(page, package["ContentPackageId"])
                if self._publication_date(data["info"]) != day:
                    raise RuntimeError("la date de l'édition ouverte ne correspond pas.")
                self._assemble(page, data, dest)
                saved += 1
                print(f"[{self.source_name}] {dest.name} ({dest.stat().st_size // 1_000_000} Mo, kiosque)")
            except Exception as e:
                failures += 1
                print(f"[{self.source_name}] ÉCHEC {day} (kiosque) : {e}")
            time.sleep(_PAUSE_SECONDS)
        return saved, failures

    def _backfill_archive(self, page: Page, since: date | None, until: date | None) -> tuple[int, int]:
        """Page d'archives (de 1 à 3 mois) : retourne (enregistrées, échecs)."""
        page.goto(self._ARCHIVE_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(4_000)
        if "secure.lemonde.fr" in page.url:
            raise RuntimeError(
                f"{self.source_name} : session expirée. Relancer : python run.py login {self.session_name}"
            )
        stamps = page.locator("a[href*='/archives/2']").evaluate_all(
            "els => els.map(e => e.getAttribute('href').split('/').pop())"
        )
        saved = failures = 0
        for stamp in sorted(set(stamps), reverse=True):
            day = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
            dest = self._path_for(day)
            if not self._in_range(day, since, until) or dest.exists():
                continue
            try:
                response = page.request.get(f"{self._ARCHIVE_URL}/{stamp}", timeout=300_000)
                if not response.ok:
                    raise RuntimeError(f"HTTP {response.status}")
                self.write_pdf(dest, response.body())
                saved += 1
                print(f"[{self.source_name}] {dest.name} ({dest.stat().st_size // 1_000_000} Mo, archives)")
            except Exception as e:
                failures += 1
                print(f"[{self.source_name}] ÉCHEC {day} (archives) : {e}")
            time.sleep(_PAUSE_SECONDS)
        return saved, failures

    def backfill(self, playwright: Playwright, since: date | None, until: date | None) -> int:
        browser, context = self.open_context(playwright)
        try:
            page = context.new_page()
            kiosk_saved, kiosk_failures = self._backfill_kiosk(page, since, until)
            archive_saved, archive_failures = self._backfill_archive(page, since, until)
        finally:
            browser.close()
        failures = kiosk_failures + archive_failures
        print(
            f"[{self.source_name}] Rattrapage terminé : {kiosk_saved} depuis le kiosque, "
            f"{archive_saved} depuis les archives, {failures} échecs."
        )
        return failures
