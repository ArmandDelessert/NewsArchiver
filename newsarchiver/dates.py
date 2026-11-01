import re
from datetime import date, timedelta

MOIS = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12,
}
_DATE_RE = re.compile(r"(\d{1,2})\s*(?:er)?\s+([a-zéûè]+)\s+(\d{4})", re.IGNORECASE)
_DIMANCHE = 6


def parse_french_date(text: str) -> date | None:
    """Extrait la première date du type « 30 octobre 2026 » (1er accepté)."""
    for day, month, year in _DATE_RE.findall(text):
        if month.lower() in MOIS:
            return date(int(year), MOIS[month.lower()], int(day))
    return None


def last_issue_date_without_sunday() -> date:
    """Date de la dernière édition attendue d'un quotidien sans parution le dimanche."""
    today = date.today()
    return today - timedelta(days=1) if today.weekday() == _DIMANCHE else today
