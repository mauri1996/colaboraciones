"""Configuración leída de .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
INBOX_DIR = DATA_DIR / "inbox"
TEMPLATES_DIR = Path(__file__).resolve().parent / "web" / "templates"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    telegram_bot_username: str = "mauri_daysi_compras_bot"
    telegram_allowed_ids: str = ""
    person_a_name: str = "Mauri"
    person_a_telegram_id: str = ""
    person_b_name: str = "Daysi"
    person_b_telegram_id: str = ""

    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    groq_api_key: str = ""
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    timezone: str = "America/Guayaquil"
    currency: str = "USD"
    default_split: str = "shared"
    web_host: str = "127.0.0.1"
    web_port: int = 8000
    enable_bot: bool = False
    panel_user: str = "hogar"
    panel_password: str = ""
    chart_color_a: str = "#2563EB"
    chart_color_b: str = "#7C3AED"

    @property
    def sqlite_path(self) -> Path:
        return DATA_DIR / "contabilizador.db"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.sqlite_path.as_posix()}"

    @property
    def alembic_database_url(self) -> str:
        return f"sqlite:///{self.sqlite_path.as_posix()}"

    @property
    def telegram_configured(self) -> bool:
        token = self.telegram_bot_token.strip()
        return bool(token) and ":" in token

    @property
    def gemini_configured(self) -> bool:
        key = self.gemini_api_key.strip()
        return bool(key) and not key.startswith("test-key")

    @property
    def allowed_telegram_ids(self) -> list[int]:
        ids: list[int] = []
        chunks = [
            self.telegram_allowed_ids,
            self.person_a_telegram_id,
            self.person_b_telegram_id,
        ]
        for chunk in chunks:
            for raw in chunk.split(","):
                raw = raw.strip()
                if raw.isdigit():
                    ids.append(int(raw))
        return list(dict.fromkeys(ids))

    @property
    def chart_colors(self) -> tuple[str, str]:
        return (
            _hex_color(self.chart_color_a, "#2563EB"),
            _hex_color(self.chart_color_b, "#7C3AED"),
        )


def _hex_color(raw: str, fallback: str) -> str:
    value = (raw or "").strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value):
        return f"#{value.upper()}"
    return fallback


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
