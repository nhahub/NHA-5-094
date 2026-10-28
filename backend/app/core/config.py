from __future__ import annotations

import ipaddress
import json
from typing import List, Optional, Union
from urllib.parse import unquote, urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_KNOWN_MODEL_PROVIDERS = {
    "groq",
    "gemini",
    "ollama",
    "openai",
    "openai_compatible",
    "llm7",
    "kilo",
    "cloudflare",
    "huggingface_api",
}
_PROVIDER_ALIASES = {
    "openai": "openai_compatible",
    "openai_compatible": "openai_compatible",
}
_DEVELOPMENT_SECRET_VALUES = {
    "default_development_secret_key_change_in_production",
    "change_this_to_a_long_random_secret_key_in_production",
    "change_this_to_a_secure_random_32_byte_secret_key",
    "change_this_to_a_long_random_secret_key",
    "secret",
    "secret_key",
    "changeme",
    "change-me",
}
_DEVELOPMENT_DATABASE_PASSWORDS = {
    "verifia_password",
    "postgres",
    "password",
    "changeme",
    "change-me",
    "minioadmin",
}
_DEVELOPMENT_DATABASE_PASSWORD_MARKERS = ("change_this", "replace_me", "example", "default")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application & Core Settings
    APP_NAME: str = "VerifiaAI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_DOCS_ENABLED: Optional[bool] = None

    # Security & Authentication
    SECRET_KEY: str = "default_development_secret_key_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @field_validator("APP_ENV", mode="before")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        normalized = {"dev": "development", "prod": "production"}.get(normalized, normalized)
        if normalized not in {"development", "test", "testing", "staging", "production"}:
            raise ValueError("APP_ENV must be development, test, staging, or production.")
        return normalized

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("["):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise ValueError("BACKEND_CORS_ORIGINS must be valid JSON or comma-separated.") from exc
            else:
                return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        raise ValueError("BACKEND_CORS_ORIGINS must be a list or comma-separated origins.")

    # Explicit policy for outbound model requests. Production defaults to deny.
    # Allowlist entries pin provider, model, and endpoint origin:
    # groq:qwen/qwen3.8-27b|https://api.groq.com
    EXTERNAL_MODEL_DATA_POLICY: Optional[str] = None
    EXTERNAL_MODEL_ALLOWED_ROUTES: List[str] = Field(default_factory=list)

    @field_validator("EXTERNAL_MODEL_DATA_POLICY", mode="before")
    @classmethod
    def normalize_external_model_policy(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        normalized = str(value).strip().lower()
        if normalized not in {"allow", "deny", "allowlist"}:
            raise ValueError("EXTERNAL_MODEL_DATA_POLICY must be allow, deny, or allowlist.")
        return normalized

    @field_validator("EXTERNAL_MODEL_ALLOWED_ROUTES", mode="before")
    @classmethod
    def parse_external_model_routes(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("["):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "EXTERNAL_MODEL_ALLOWED_ROUTES must be valid JSON or comma-separated."
                    ) from exc
            else:
                value = [route.strip() for route in value.split(",") if route.strip()]
        if not isinstance(value, list):
            raise ValueError("EXTERNAL_MODEL_ALLOWED_ROUTES must be a list.")

        routes: list[str] = []
        for raw_route in value:
            route_and_origin, origin_separator, origin = str(raw_route).partition("|")
            provider, separator, model = route_and_origin.partition(":")
            provider = provider.strip().lower()
            model = model.strip()
            if (
                not separator
                or not origin_separator
                or not provider
                or not model
                or model == "*"
                or "|" in origin
            ):
                raise ValueError(
                    "Allowed model routes must use provider:model|https://exact-origin."
                )
            if provider not in _KNOWN_MODEL_PROVIDERS:
                raise ValueError(f"Unsupported provider in EXTERNAL_MODEL_ALLOWED_ROUTES: {provider}.")
            canonical_provider = _PROVIDER_ALIASES.get(provider, provider)
            origin = cls._normalize_endpoint_origin(origin)
            route = f"{canonical_provider}:{model}|{origin}"
            if route not in routes:
                routes.append(route)
        return routes

    @staticmethod
    def _normalize_endpoint_origin(endpoint_url: str) -> str:
        """Return a normalized HTTP(S) origin, rejecting URL credentials and parameters."""
        try:
            parsed = urlsplit(str(endpoint_url).strip())
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Model route endpoint must be a valid HTTP(S) origin.") from exc

        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        if (
            scheme not in {"http", "https"}
            or not hostname
            or "*" in hostname
            or "%" in hostname
            or any(character.isspace() for character in hostname)
            or "\\" in hostname
            or port == 0
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "Model route endpoint must be an exact HTTP(S) origin without credentials or a path."
            )

        # Canonicalize IPv6 brackets and omit explicit default ports.
        rendered_host = f"[{hostname}]" if ":" in hostname else hostname
        if port is not None and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
            rendered_host = f"{rendered_host}:{port}"
        return f"{scheme}://{rendered_host}"

    @staticmethod
    def _is_local_hostname(hostname: str) -> bool:
        normalized = hostname.strip().lower().rstrip(".")
        if normalized in {"localhost", "localhost.localdomain", "host.docker.internal"}:
            return True
        if normalized.endswith(".localhost"):
            return True
        try:
            address = ipaddress.ip_address(normalized)
        except ValueError:
            return False
        mapped_ipv4 = getattr(address, "ipv4_mapped", None)
        return (
            address.is_loopback
            or address.is_unspecified
            or bool(mapped_ipv4 and mapped_ipv4.is_loopback)
        )

    # Production uploads remain disabled unless an operator explicitly accepts
    # the unscanned-file risk. A scanner integration can replace this policy later.
    ALLOW_UNSCANNED_UPLOADS: Optional[bool] = None

    # Database Settings (PostgreSQL + pgvector)
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "verifia_db"
    POSTGRES_USER: str = "verifia_user"
    POSTGRES_PASSWORD: str = "verifia_password"
    DATABASE_URL: Optional[str] = None
    ASYNC_DATABASE_URL: Optional[str] = None

    @property
    def sync_database_uri(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def async_database_uri(self) -> str:
        if self.ASYNC_DATABASE_URL:
            return self.ASYNC_DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Cache & Message Broker (Redis)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: Optional[str] = None

    @property
    def redis_uri(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Storage Settings
    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_PATH: str = "./data/storage"
    DOCUMENT_MAX_FILE_SIZE_BYTES: int = 20 * 1024 * 1024
    REQUEST_MAX_BODY_SIZE_BYTES: int = 22 * 1024 * 1024
    DOCUMENT_MAX_ARCHIVE_ENTRIES: int = 2048
    DOCUMENT_MAX_ARCHIVE_EXPANDED_SIZE_BYTES: int = 100 * 1024 * 1024
    DOCUMENT_MAX_ARCHIVE_ENTRY_SIZE_BYTES: int = 32 * 1024 * 1024
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "verifia-documents"
    MINIO_SECURE: bool = False

    # AI Models & Gateways
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_DOCUMENT_MODEL: str = "gemini-3.8-flash"
    GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"
    GEMINI_REQUEST_TIMEOUT_SECONDS: int = 120
    GEMINI_MAX_RETRIES: int = 3
    GEMINI_RETRY_BASE_SECONDS: float = 1.0
    GROQ_API_KEY: Optional[str] = None
    GROQ_API_KEY_FALLBACK_1: Optional[str] = None
    GROQ_API_KEY_FALLBACK_2: Optional[str] = None
    GROQ_DOCUMENT_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_API_BASE_URL: str = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_REQUEST_TIMEOUT_SECONDS: int = 120
    GROQ_MAX_RETRIES: int = 2
    GROQ_RETRY_BASE_SECONDS: float = 1.0
    LLM7_API_KEY: Optional[str] = None
    LLM7_API_BASE_URL: str = "https://api.llm7.io/v1/chat/completions"
    LLM7_DOCUMENT_MODEL: str = "gpt-oss:20b"
    KILO_API_KEY: Optional[str] = None
    KILO_API_BASE_URL: str = "https://api.kilo.ai/api/gateway/chat/completions"
    KILO_DOCUMENT_MODEL: str = "dots-studio/dots-3-note-preview:free"
    # Agent-specific routing can spread inference traffic across configured APIs.
    DOCUMENT_MODEL_PROVIDER: str = "llm7"
    DOCUMENT_MODEL: Optional[str] = None
    VERIFICATION_MODEL_PROVIDER: str = "groq"
    VERIFICATION_MODEL: Optional[str] = None
    WORKFLOW_MODEL_PROVIDER: str = "kilo"
    WORKFLOW_MODEL: Optional[str] = "dots-studio/dots-3-note-preview:free"
    SUPERVISOR_MODEL_PROVIDER: str = "groq"
    SUPERVISOR_MODEL: Optional[str] = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_DOCUMENT: str = "llama3.2"
    OLLAMA_REQUEST_TIMEOUT_SECONDS: int = 120
    DOCUMENT_MODEL_MAX_TEXT_CHARS: int = 100000
    DOCUMENT_REVIEW_CONFIDENCE_THRESHOLD: float = 0.7
    CASE_ORCHESTRATION_ENABLED: bool = True
    OLLAMA_MODEL_VERIFICATION: str = "llama3.2"
    OLLAMA_MODEL_WORKFLOW: str = "llama3.2"
    OCR_ENGINE: str = "tesseract"
    TESSERACT_CMD: Optional[str] = None
    OCR_LANGUAGE: str = "eng"
    OCR_TIMEOUT_SECONDS: int = 30
    OCR_DPI: int = 220
    EMBEDDING_PROVIDER: str = "cloudflare"
    EMBEDDING_MODEL_NAME: str = "@cf/baai/bge-m3"
    CLOUDFLARE_ACCOUNT_ID: Optional[str] = None
    CLOUDFLARE_API_TOKEN: Optional[str] = None
    CLOUDFLARE_AI_BASE_URL: str = "https://api.cloudflare.com/client/v4"
    EMBEDDING_API_URL: Optional[str] = None
    EMBEDDING_DEVICE: str = "cpu"
    HUGGINGFACE_HUB_TOKEN: Optional[str] = None

    # Observability & Logging
    LOG_LEVEL: str = "INFO"
    ENABLE_AUDIT_LOG: bool = True

    def validate_security_settings(self) -> None:
        if self.DOCUMENT_MAX_FILE_SIZE_BYTES <= 0 or self.REQUEST_MAX_BODY_SIZE_BYTES <= 0:
            raise RuntimeError("Upload and request body size limits must be positive.")
        if self.REQUEST_MAX_BODY_SIZE_BYTES < self.DOCUMENT_MAX_FILE_SIZE_BYTES:
            raise RuntimeError("REQUEST_MAX_BODY_SIZE_BYTES must include the maximum document size.")
        if self.APP_ENV not in {"production", "staging"}:
            return

        errors: list[str] = []
        secret = self.SECRET_KEY.strip()
        if (
            len(secret.encode("utf-8")) < 32
            or len(set(secret)) < 8
            or secret.lower() in _DEVELOPMENT_SECRET_VALUES
            or any(marker in secret.lower() for marker in ("change_this", "replace_me", "example_secret"))
        ):
            errors.append("SECRET_KEY must be a unique random value of at least 32 bytes.")
        if self.DEBUG:
            errors.append("DEBUG must be false in production.")
        if self.ALLOW_UNSCANNED_UPLOADS is True:
            errors.append(
                "ALLOW_UNSCANNED_UPLOADS must be false in production until a malware scanner is configured."
            )
        if not self.BACKEND_CORS_ORIGINS:
            errors.append("BACKEND_CORS_ORIGINS must contain the deployed HTTPS frontend origin.")
        for origin in self.BACKEND_CORS_ORIGINS:
            parsed = urlsplit(origin)
            try:
                port = parsed.port
            except ValueError:
                port = -1
            if (
                origin == "*"
                or parsed.scheme != "https"
                or not parsed.hostname
                or self._is_local_hostname(parsed.hostname)
                or "*" in parsed.hostname
                or parsed.netloc != parsed.netloc.lower()
                or port == 443
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path != ""
                or parsed.query
                or parsed.fragment
                or origin != f"https://{parsed.netloc}"
            ):
                errors.append("Every production CORS origin must be an exact HTTPS origin without a path.")
                break

        database_targets: list[tuple[str, int, str, str, str, str]] = []
        for setting_name, database_url, expected_scheme in (
            ("DATABASE_URL", self.DATABASE_URL, "postgresql+psycopg2"),
            ("ASYNC_DATABASE_URL", self.ASYNC_DATABASE_URL, "postgresql+asyncpg"),
        ):
            if not database_url:
                errors.append(f"{setting_name} must be explicitly configured in production.")
                continue
            try:
                parsed = urlsplit(database_url)
                hostname = (parsed.hostname or "").lower()
                port = parsed.port or 5432
                username = unquote(parsed.username or "")
                password = unquote(parsed.password or "")
                database_name = unquote(parsed.path.lstrip("/"))
            except ValueError:
                errors.append(f"{setting_name} must be a valid PostgreSQL URL.")
                continue
            if (
                parsed.scheme != expected_scheme
                or not hostname
                or self._is_local_hostname(hostname)
                or not username
                or len(password.encode("utf-8")) < 24
                or len(set(password)) < 8
                or password.lower() in _DEVELOPMENT_DATABASE_PASSWORDS
                or any(marker in password.lower() for marker in _DEVELOPMENT_DATABASE_PASSWORD_MARKERS)
                or not database_name
                or parsed.port == 0
                or parsed.query
                or parsed.fragment
            ):
                errors.append(f"{setting_name} must use a remote service host and unique credentials.")
            else:
                database_targets.append(
                    (hostname, port, username, password, database_name, setting_name)
                )

        if len(database_targets) == 2 and database_targets[0][:5] != database_targets[1][:5]:
            errors.append("DATABASE_URL and ASYNC_DATABASE_URL must target the same database and credentials.")

        if not self.REDIS_URL:
            errors.append("REDIS_URL must explicitly configure the production cache service.")
        else:
            try:
                redis_url = urlsplit(self.REDIS_URL)
                redis_hostname = redis_url.hostname or ""
                redis_password = unquote(redis_url.password or "")
                _ = redis_url.port
            except ValueError:
                errors.append("REDIS_URL must be a valid TLS-enabled Redis URL.")
            else:
                if (
                    redis_url.scheme != "rediss"
                    or not redis_hostname
                    or self._is_local_hostname(redis_hostname)
                    or redis_url.fragment
                    or len(redis_password.encode("utf-8")) < 24
                    or len(set(redis_password)) < 8
                    or redis_password.lower() in _DEVELOPMENT_DATABASE_PASSWORDS
                    or any(
                        marker in redis_password.lower()
                        for marker in _DEVELOPMENT_DATABASE_PASSWORD_MARKERS
                    )
                ):
                    errors.append("REDIS_URL must use a remote TLS Redis service with unique credentials.")

        policy = self.effective_external_model_data_policy
        if policy == "allow":
            errors.append("Production cannot use EXTERNAL_MODEL_DATA_POLICY=allow; choose deny or allowlist.")
        if policy == "allowlist" and not self.EXTERNAL_MODEL_ALLOWED_ROUTES:
            errors.append("EXTERNAL_MODEL_ALLOWED_ROUTES is required when the policy is allowlist.")
        if policy == "deny" and self.EXTERNAL_MODEL_ALLOWED_ROUTES:
            errors.append("Remove EXTERNAL_MODEL_ALLOWED_ROUTES or change the policy from deny.")
        if policy == "allowlist":
            for route in self.EXTERNAL_MODEL_ALLOWED_ROUTES:
                _, _, origin = route.partition("|")
                if not origin.startswith("https://"):
                    errors.append("Production model allowlist endpoints must use HTTPS.")
                    break

        if errors:
            raise RuntimeError("Unsafe production settings: " + " ".join(errors))

    @property
    def api_docs_enabled(self) -> bool:
        if self.API_DOCS_ENABLED is not None:
            return self.API_DOCS_ENABLED
        return self.APP_ENV in {"development", "test", "testing"}

    @property
    def allow_unscanned_uploads(self) -> bool:
        if self.ALLOW_UNSCANNED_UPLOADS is not None:
            return self.ALLOW_UNSCANNED_UPLOADS
        return self.APP_ENV in {"development", "test", "testing"}

    @property
    def effective_external_model_data_policy(self) -> str:
        if self.EXTERNAL_MODEL_DATA_POLICY:
            return self.EXTERNAL_MODEL_DATA_POLICY
        return "allow" if self.APP_ENV in {"development", "test", "testing"} else "deny"

    def require_model_route_allowed(
        self,
        provider: str,
        model: str,
        endpoint_url: Optional[str] = None,
    ) -> None:
        provider_name = provider.strip().lower()
        canonical_provider = _PROVIDER_ALIASES.get(provider_name, provider_name)
        if canonical_provider in {"fake", "mock", "test"}:
            if self.APP_ENV in {"production", "staging"}:
                raise ValueError("Test model providers are disabled in production-like environments.")
            return

        policy = self.effective_external_model_data_policy
        if policy == "allow":
            if self.APP_ENV in {"production", "staging"}:
                raise ValueError("Unrestricted model routes are disabled in production-like environments.")
            return
        if policy == "deny":
            raise ValueError("Model route is disabled by EXTERNAL_MODEL_DATA_POLICY.")

        if not endpoint_url:
            raise ValueError("Model route endpoint is required by EXTERNAL_MODEL_ALLOWED_ROUTES.")
        origin = self._normalize_endpoint_origin(endpoint_url)
        if self.APP_ENV in {"production", "staging"} and not origin.startswith("https://"):
            raise ValueError("Production model routes require an HTTPS endpoint.")
        route = f"{canonical_provider}:{model.strip()}|{origin}"
        if route not in self.EXTERNAL_MODEL_ALLOWED_ROUTES:
            raise ValueError(
                "Model route and endpoint are not approved by EXTERNAL_MODEL_ALLOWED_ROUTES."
            )

    def require_embedding_route_allowed(
        self,
        provider: str,
        model: str,
        endpoint_url: Optional[str] = None,
    ) -> None:
        provider_name = provider.strip().lower()
        if provider_name == "local":
            return
        self.require_model_route_allowed(provider_name, model, endpoint_url)


settings = Settings()
settings.validate_security_settings()
