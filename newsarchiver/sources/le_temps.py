import time
from datetime import date
from pathlib import Path
from playwright.sync_api import Page, Playwright, Response

from newsarchiver.base import BaseDownloader
from newsarchiver.dates import last_issue_date_without_sunday, parse_french_date

# Une édition complète pèse des dizaines de Mo ; en dessous, c'est une page ou un extrait.
_MIN_PDF_BYTES = 2_000_000
_WAIT_SECONDS = 120


def _looks_like_pdf(response: Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    return "pdf" in content_type or response.url.split("?")[0].lower().endswith(".pdf")


class LeTempsDownloader(BaseDownloader):

    source_name = "Le Temps"
    session_name = "letemps"
    _LIST_URL = "https://www.letemps.ch/pdf?publication=TPS"
    _EDITION_CARD = ".lt-card-print-edition"

    def _path_for(self, publication_date: date) -> Path:
        folder = self.config.archive_path / "Le Temps" / str(publication_date.year)
        return folder / f"LeTemps_{publication_date.isoformat()}.pdf"

    def already_archived(self) -> bool:
        return self._path_for(last_issue_date_without_sunday()).exists()

    def _latest_edition(self, page: Page) -> tuple[date, str]:
        """Dernière édition publiée (liste publique) : date et lien vers le lecteur."""
        page.goto(self._LIST_URL, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_selector(self._EDITION_CARD, timeout=15_000)
        for card in page.locator(self._EDITION_CARD).all():
            link = card.locator("a[href$='/epaper/redirect']").first
            if link.count() == 0:  # édition du jour pas encore publiée
                continue
            publication_date = parse_french_date(card.inner_text())
            if publication_date:
                return publication_date, "https://www.letemps.ch" + link.get_attribute("href")
        raise RuntimeError(f"{self.source_name} : aucune édition trouvée sur {self._LIST_URL}")

    def login(self, playwright: Playwright) -> None:
        # La connexion reste manuelle : aucun mot de passe n'est stocké.
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            context.new_page().goto("https://www.letemps.ch/compte/connexion")
            print(
                f"[{self.source_name}] Connecte-toi dans la fenêtre du navigateur "
                "(coche « Se souvenir de moi »), puis reviens ici."
            )
            input("Appuie sur Entrée une fois connecté… ")
            context.storage_state(path=str(self.session_path))
        finally:
            browser.close()
        print(f"[{self.source_name}] Session enregistrée : {self.session_path}")

    def _open_reader(self, page: Page, reader_url: str) -> list[Response]:
        """Ouvre le lecteur en enregistrant toutes les réponses réseau."""
        responses: list[Response] = []
        page.context.on("response", lambda response: responses.append(response))
        page.goto(reader_url, wait_until="domcontentloaded", timeout=60_000)
        if "/compte/connexion" in page.url:
            raise RuntimeError(
                f"{self.source_name} : session expirée. "
                f"Relancer : python run.py login {self.session_name}"
            )
        return responses

    def download(self, page: Page) -> Path | None:
        publication_date, reader_url = self._latest_edition(page)
        dest = self._path_for(publication_date)
        if dest.exists():
            print(
                f"[{self.source_name}] La dernière édition ({dest.name}) est déjà "
                "archivée, la nouvelle n'est peut-être pas encore en ligne."
            )
            return None

        responses = self._open_reader(page, reader_url)

        # Interception réseau : on attend le PDF complet envoyé au lecteur.
        deadline = time.monotonic() + _WAIT_SECONDS
        checked: set[int] = set()
        while time.monotonic() < deadline:
            for response in list(responses):
                if id(response) in checked or not _looks_like_pdf(response):
                    continue
                checked.add(id(response))
                body = response.body()
                if len(body) >= _MIN_PDF_BYTES and body[:5] == b"%PDF-":
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    partial = dest.with_name(dest.name + ".part")
                    partial.write_bytes(body)
                    partial.replace(dest)
                    return dest
            page.wait_for_timeout(1_000)

        seen = [r.url[:120] for r in responses if _looks_like_pdf(r)]
        raise RuntimeError(
            f"{self.source_name} : aucun PDF complet intercepté en {_WAIT_SECONDS} s "
            f"(PDF vus : {seen or 'aucun'}). Lancer : python run.py probe letemps"
        )

    def probe(self, playwright: Playwright) -> None:
        """Diagnostic : enregistre le trafic réseau du lecteur dans un fichier texte."""
        session = self.session_path
        if not session.exists():
            raise RuntimeError(f"Session absente. Lancer : python run.py login {self.session_name}")
        browser = playwright.chromium.launch(headless=not self.config.debug)
        try:
            context = browser.new_context(
                storage_state=str(session), viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            publication_date, reader_url = self._latest_edition(page)
            responses = self._open_reader(page, reader_url)
            page.wait_for_timeout(45_000)
            out = self.config.browser_state_dir / f"probe_{self.session_name}.txt"
            lines = [f"édition {publication_date} -> {reader_url}", f"page finale : {page.url}", ""]
            for r in responses:
                if r.request.resource_type in ("image", "font", "stylesheet", "media"):
                    continue
                size = r.headers.get("content-length", "?")
                lines.append(
                    f"{r.status} {r.request.resource_type:9} {r.headers.get('content-type', '')[:30]:30} "
                    f"{size:>10} {r.url[:200]}"
                )
            out.write_text("\n".join(lines), encoding="utf-8")
            page.screenshot(path=str(out.with_suffix(".png")))
        finally:
            browser.close()
        print(f"[{self.source_name}] Trafic enregistré : {out} (+ capture .png)")
