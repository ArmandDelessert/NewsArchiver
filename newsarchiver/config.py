from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class Config:
    archive_path: Path
    debug: bool


def load_config() -> Config:
    return Config(
        archive_path=Path(os.environ["ARCHIVE_PATH"]),
        debug=os.environ.get("DEBUG", "").lower() == "true",
    )
