from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

VALID_STATUSES = ("New", "Queued", "Played", "Skipped")
FILTER_STATUSES = ("All", "New", "Queued", "Played")


def _env_with_fallback(name: str, default: str, *, invalid_values: tuple[str, ...] = ()) -> str:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    value = raw_value.strip()
    if not value or value in invalid_values:
        return default

    return value


def _resolve_data_dir() -> Path:
    configured = os.getenv("DATA_DIR", "").strip()
    railway_volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if not configured:
        if railway_volume:
            configured = railway_volume
        else:
            return BASE_DIR

    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


def _resolve_database_path(data_dir: Path) -> Path:
    configured = os.getenv("DATABASE_FILE", "gig_requests.db").strip()
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = (data_dir / path).resolve()
    return path


DATA_DIR = _resolve_data_dir()
DATABASE_PATH = _resolve_database_path(DATA_DIR)


@dataclass(frozen=True)
class Settings:
    site_title: str = _env_with_fallback(
        "SITE_TITLE",
        "Scalla Song Requests",
        invalid_values=("Tonight's Song Requests",),
    )
    performer_name: str = _env_with_fallback(
        "PERFORMER_NAME",
        "Scalla",
        invalid_values=("Your Performer Name",),
    )
    admin_password: str = os.getenv("ADMIN_PASSWORD", "changeme")
    asset_version: str = os.getenv("ASSET_VERSION", "20260416-brandfix")
    venmo_url: str = _env_with_fallback(
        "VENMO_URL",
        "https://account.venmo.com/u/Sean-Garry-4",
        invalid_values=("https://venmo.com/", "https://venmo.com/your-handle"),
    )
    instagram_url: str = _env_with_fallback(
        "INSTAGRAM_URL",
        "https://instagram.com/_scalla__",
        invalid_values=("https://instagram.com/", "https://instagram.com/your-handle"),
    )
    booking_email: str = _env_with_fallback(
        "BOOKING_EMAIL",
        "seansgarry@gmail.com",
        invalid_values=("you@example.com",),
    )
    booking_subject: str = os.getenv("BOOKING_SUBJECT", "!!!GIG BOOKING REQUEST!!!")
    web3forms_access_key: str = os.getenv("WEB3FORMS_ACCESS_KEY", "").strip()
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = _env_with_fallback(
        "SMTP_USERNAME",
        "seansgarry@gmail.com",
        invalid_values=("you@example.com",),
    )
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email: str = _env_with_fallback(
        "SMTP_FROM_EMAIL",
        "seansgarry@gmail.com",
        invalid_values=("you@example.com",),
    )
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
    secret_key: str = os.getenv("SECRET_KEY", "replace-this-secret-key")
    base_url: str = os.getenv("BASE_URL", "").strip()
    data_dir: Path = DATA_DIR
    database_path: Path = DATABASE_PATH


settings = Settings()
