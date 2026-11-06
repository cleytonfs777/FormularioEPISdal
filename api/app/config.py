from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(API_ROOT / ".env"),
        extra="ignore",
    )

    # Banco
    database_url: str = "sqlite:///./epi.db"
    # WAL quebra em bind-mount NTFS/Docker Desktop; use DELETE no compose.
    sqlite_journal_mode: str = "WAL"

    # Autenticação simples por secret compartilhado (header X-Secret-Code)
    secret_code: str = "TROQUE_ESTE_SEGREDO"

    # Painel admin (sessão em cookie HttpOnly)
    session_secret: str = "TROQUE_O_SESSION_SECRET"
    admin_csrf_ttl_seconds: int = 3600
    login_rate_limit: int = 8
    login_rate_window_seconds: int = 600

    # Google Sheets
    google_credentials_file: str = "app/service_account.json"
    spreadsheet_id: str = ""
    sheet_name: str = "Relação Nominal"  # nome da ABA (não o arquivo)
    sheet_header_row: int = 1

    # Sincronização (DB sujo → planilha, depois planilha → novos registros)
    sync_interval_seconds: int = 300

    # CORS
    allowed_origins: str = "*"

    # Proxy corporativo. Deixe vazio se não houver.
    https_proxy: str = ""

    @model_validator(mode="after")
    def resolve_paths(self):
        cred = Path(self.google_credentials_file)
        candidates = [
            cred,
            API_ROOT / cred,
            API_ROOT / "app" / cred.name,
            API_ROOT / "app" / "service_account.json",
        ]
        for c in candidates:
            if c.is_file():
                self.google_credentials_file = str(c.resolve())
                break

        url = self.database_url
        if url.startswith("sqlite:///"):
            rest = url[len("sqlite:///"):]
            # Windows: sqlite:///D:/... já é absoluto
            path = Path(rest)
            if rest.startswith("./"):
                path = API_ROOT / rest[2:]
            elif not path.is_absolute():
                path = API_ROOT / rest
            self.database_url = "sqlite:///" + path.resolve().as_posix()

        if self.sync_interval_seconds < 30:
            self.sync_interval_seconds = 30

        mode = (self.sqlite_journal_mode or "WAL").strip().upper()
        if mode not in {"WAL", "DELETE", "TRUNCATE", "MEMORY", "OFF"}:
            mode = "WAL"
        self.sqlite_journal_mode = mode

        return self


settings = Settings()
