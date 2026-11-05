"""Application configuration.

All settings are read from environment variables, with sane defaults. A local
SQLite file is used by default, but any SQLAlchemy database URL (e.g. a remote
PostgreSQL or MySQL instance) can be provided through ``DATABASE_URL``.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Web / app ---------------------------------------------------------
    app_title: str = "Blast server (v2.2.29+)"
    # URL prefix under which the app is exposed by the reverse proxy (which
    # must strip it before forwarding). Any of "", "/", "blast", "/blast",
    # "/blast/" is accepted and normalized to "" or "/blast" (leading slash,
    # no trailing slash). Always build URLs with ``url()`` / ``external_url()``.
    base_url_path: str = ""
    upload_limit: int = 100  # MiB, per uploaded file / pasted sequence
    # Max job submissions per client IP per minute (0 = disabled).
    submit_rate_limit: int = 10

    # Optional directory mounted into the container that is searched *before*
    # the built-in templates. Drop a custom ``layout.html`` (and any other
    # template) there to override the default rendering.
    templates_override_dir: str = ""

    # Optional directory mounted into the container that serves custom static
    # assets (css, images, ...) at ``{base_url_path}/static/custom/``.
    static_override_dir: str = ""

    # Optional extra stylesheet, either a full URL or a filename relative to
    # ``static_override_dir`` (e.g. "custom.css" -> /static/custom/custom.css).
    # When set it is linked from the layout's <head>.
    custom_css: str = ""

    # --- Database ----------------------------------------------------------
    # Either a full SQLAlchemy URL (sqlite:///..., postgresql://..., mysql://...)
    # or leave empty to build one from the DB_* variables below.
    database_url: str = ""

    # Legacy style connection parameters (used when database_url is empty).
    db_driver: str = "sqlite"  # sqlite, pgsql, mysql, ...
    db_host: str = ""
    db_port: str = ""
    db_name: str = ""
    db_user: str = ""
    db_pass: str = ""

    # --- Slurm REST API -----------------------------------------------------
    slurm_rest_url: str = "http://slurmctld:6820"
    slurm_api_version: str = "v0.0.40"
    slurm_verify_tls: bool = True  # set False to skip TLS verification
    slurm_jwt: str = ""            # the JWT token
    slurm_jwt_file: str = ""       # optional file containing the JWT token
    slurm_user: str = ""           # submit jobs as this user (X-SLURM-USER-NAME)
    slurm_partition: str = ""
    slurm_qos: str = ""
    slurm_account: str = ""
    jobs_drmaa_native: str = ""         # extra sbatch option string
    # Once a job has been inactive for longer than this many seconds, poll the
    # slurmdb endpoint instead of the (live-cluster) slurm endpoint.
    slurm_inactive_timeout: int = 600

    # --- Jobs ---------------------------------------------------------------
    jobs_method: str = "slurm"     # only "slurm" is supported in this rewrite
    jobs_work_dir: str = str(Path("/tmp/"))
    jobs_sched_name: str = "blast"
    result_url_host: str = ""      # e.g. https://my.server (empty = same host); a trailing "/" is ignored
    cdd_delta_path: str = ""
    pre_cmd: str = ""
    link_command: str = (
        "python3 ./bin/blast_links.py "
        "--config ./bin/links.yml --gff-url $GFF3_URL"
    )

    # --- Blast databank -----------------------------------------------------
    banks_config: str = str(PROJECT_DIR / "config" / "banks.yml")
    links_config: str = str(PROJECT_DIR / "config" / "links.yml")
    # --- Mail ---------------------------------------------------------------
    admin_email: str = "admin@blast-server"
    admin_name: str = "Blast admin"
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_use_tls: bool = False

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.db_driver == "sqlite":
            # A local sqlite file next to the project
            path = self.db_name or (PROJECT_DIR / "blast.db")
            return f"sqlite:///{path}"
        driver_map = {
            "pgsql": "postgresql+psycopg2",
            "mysql": "mysql+pymysql",
        }
        driver = driver_map.get(self.db_driver, self.db_driver)
        auth = ""
        if self.db_user:
            auth = self.db_user
            if self.db_pass:
                auth += f":{self.db_pass}"
            auth += "@"
        host = self.db_host
        if self.db_port:
            host = f"{host}:{self.db_port}"
        return f"{driver}://{auth}{host}/{self.db_name}"

    @property
    def slurm_token(self) -> str:
        if self.slurm_jwt:
            return self.slurm_jwt
        if self.slurm_jwt_file:
            return Path(self.slurm_jwt_file).read_text().strip()
        return ""

    # ---- URL helpers ----------------------------------------------------
    @field_validator("base_url_path", mode="before")
    @classmethod
    def _normalize_base_url_path(cls, value):
        """Return "" or "/segment[/segment...]": one leading slash, none trailing."""
        if value is None:
            return ""
        segments = [seg for seg in str(value).strip().split("/") if seg]
        return "/" + "/".join(segments) if segments else ""

    @field_validator("result_url_host", mode="before")
    @classmethod
    def _normalize_result_url_host(cls, value):
        """Drop whitespace and trailing slashes: "https://h/" -> "https://h"."""
        return "" if value is None else str(value).strip().rstrip("/")

    def url(self, path: str = "") -> str:
        """In-app URL for ``path``, prefixed by ``base_url_path``.

        ``url()`` is the application root ("/" or "/blast/"); ``url("job/x")``
        is "/job/x" or "/blast/job/x". Leading slashes in ``path`` are ignored.
        """
        return f"{self.base_url_path}/{path.lstrip('/')}"

    def external_url(self, path: str = "") -> str:
        """Like :meth:`url`, prefixed by ``result_url_host`` (for e-mails, GFF3
        links and anything that must be valid outside the current page)."""
        return f"{self.result_url_host}{self.url(path)}"

    @property
    def result_url(self) -> str:
        return self.external_url("tmp/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
