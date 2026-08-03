from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BIFROST_", extra="ignore")

    enroll_token: str = "change-me"
    auto_approve: bool = True

    data_dir: Path = Path("/data")

    # Declarative bookmarks (YAML, synced on start and on file change).
    # Defaults to <data_dir>/bookmarks.yml or .yaml, whichever exists.
    bookmarks_file: Path | None = None

    host: str = "0.0.0.0"
    port: int = 8000

    # Agent defaults, pushed on hello_ack and changeable live from the UI later.
    metrics_interval_s: int = 10
    fs_interval_s: int = 60
    smart_interval_s: int = 1800

    # Heartbeat cadence agents must honor; misses drive degraded/offline states.
    heartbeat_interval_s: int = 15

    # Gateway domain: when set, label-less Docker services with an unambiguous
    # port get https://<container>.<domain> as card URL and gateway route.
    # Empty (the default) disables all URL derivation.
    service_domain: str = ""

    # Metric history retention per resolution.
    retention_raw_h: int = 24
    retention_1m_d: int = 14
    retention_1h_d: int = 730

    # Path to the built SPA; served when present.
    frontend_dist: Path = Path(__file__).resolve().parent.parent / "static"

    @property
    def state_db_path(self) -> Path:
        return self.data_dir / "bifrost.db"

    @property
    def metrics_db_path(self) -> Path:
        return self.data_dir / "metrics.db"


settings = Settings()
