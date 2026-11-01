from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    archive_path: Path
    browser_state_dir: Path
    debug: bool


def load_config() -> Config:
    return Config(
        archive_path=Path(os.environ["ARCHIVE_PATH"]),
        browser_state_dir=Path(
            os.environ.get("BROWSER_STATE_DIR", _PROJECT_ROOT / ".browser_state")
        ),
        debug=os.environ.get("DEBUG", "").lower() == "true",
    )
