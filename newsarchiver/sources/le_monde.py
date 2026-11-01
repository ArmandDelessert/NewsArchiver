from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from playwright.sync_api import Page, Playwright

from newsarchiver.base import BaseDownloader
from newsarchiver.dates import last_issue_date_without_sunday


def _redact(url: str) -> str:
    """Garde l'URL et les noms de paramètres, masque les valeurs (jetons possibles)."""
    parts = urlsplit(url)
    query = "&".join(f"{name}=…" for name, _ in parse_qsl(parts.query))
    return f"{parts.scheme}://{parts.netloc}{parts.path}" + (f"?{query}" if query else "")


class LeMondeDownloader(BaseDownloader):

    source_name = "Le Monde"
    session_name = "lemonde"
    # Téléchargement pas encore écrit : exclu de « python run.py » sans argument.
    ready = False
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

    def download(self, page: Page) -> Path | None:
        raise RuntimeError(
            f"{self.source_name} : téléchargement pas encore implémenté. "
            "Lancer : python run.py probe lemonde"
        )

    def probe(self, playwright: Playwright) -> None:
        """Diagnostic : ouvre le lecteur, clique sur « Lire » et journalise la page et le réseau."""
        if not self.session_path.exists():
            raise RuntimeError(f"Session absente. Lancer : python run.py login {self.session_name}")
        out = self.config.browser_state_dir / f"probe_{self.session_name}"
        browser = playwright.chromium.launch(headless=not self.config.debug)
        try:
            context = browser.new_context(
                storage_state=str(self.session_path), viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            responses = []
            context.on("response", lambda response: responses.append(response))

            lines: list[str] = []

            def snapshot(label: str) -> None:
                page.screenshot(path=f"{out}_{label}.png")
                elements = page.evaluate(
                    """() => [...document.querySelectorAll('a,button,[role=button],[class*=button],[class*=download],[class*=menu]')]
                        .filter(e => e.offsetParent !== null)
                        .map(e => `${e.tagName} | ${(e.innerText || e.title || e.getAttribute('aria-label') || '').trim().slice(0, 50)} | ${String(e.className).slice(0, 60)}`)
                        .slice(0, 80)"""
                )
                lines.extend([f"=== {label} : {_redact(page.url)}", *elements, ""])

            page.goto(self._READER_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(5_000)
            try:  # bandeau cookies : refuser
                page.get_by_text("Continuer sans accepter").first.click(timeout=3_000)
            except Exception:
                pass
            page.wait_for_timeout(2_000)
            snapshot("1_accueil")

            page.locator(".main-button", has_text="Lire").first.click(timeout=10_000)
            page.wait_for_timeout(20_000)
            snapshot("2_lecteur")

            lines.append("=== Réponses réseau (hors images, polices, styles)")
            for r in responses:
                if r.request.resource_type in ("image", "font", "stylesheet", "media"):
                    continue
                lines.append(
                    f"{r.status} {r.request.resource_type:9} "
                    f"{r.headers.get('content-type', '')[:30]:30} "
                    f"{r.headers.get('content-length', '?'):>10} {_redact(r.url)[:220]}"
                )
            Path(f"{out}.txt").write_text("\n".join(lines), encoding="utf-8")
        finally:
            browser.close()
        print(f"[{self.source_name}] Diagnostic enregistré : {out}.txt (+ captures .png)")
