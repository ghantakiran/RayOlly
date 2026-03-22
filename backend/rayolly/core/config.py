from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAYOLLY_SERVER_")

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    debug: bool = False
    log_level: str = "info"


class ClickHouseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAYOLLY_CLICKHOUSE_")

    host: str = "localhost"
    port: int = 8123
    database: str = "default"
    user: str = "rayolly"
    password: str = "rayolly_dev"
    cluster_name: str = "rayolly_cluster"
    max_connections: int = 20


class NATSSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAYOLLY_NATS_")

    url: str = "nats://rayolly_dev_token@localhost:4222"
    max_reconnects: int = 10
    reconnect_time_wait: int = 2


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAYOLLY_REDIS_")

    url: str = "redis://localhost:6379/0"
    max_connections: int = 50
    query_cache_ttl: int = 300


class S3Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAYOLLY_S3_")

    endpoint: str = "http://localhost:9000"
    bucket: str = "rayolly"
    access_key: str = ""
    secret_key: str = ""
    region: str = "us-east-1"
    path_prefix: str = "data"


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAYOLLY_AUTH_")

    jwt_secret: str = "rayolly-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    api_key_header: str = "X-RayOlly-API-Key"


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAYOLLY_AI_")

    anthropic_api_key: str = ""
    default_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    local_model_enabled: bool = False
    local_model_endpoint: str = "http://localhost:11434"


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAYOLLY_POSTGRES_")

    url: str = "postgresql+asyncpg://rayolly:rayolly@localhost:5432/rayolly"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAYOLLY_")

    server: ServerSettings = Field(default_factory=ServerSettings)
    clickhouse: ClickHouseSettings = Field(default_factory=ClickHouseSettings)
    nats: NATSSettings = Field(default_factory=NATSSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    s3: S3Settings = Field(default_factory=S3Settings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    ai: AISettings = Field(default_factory=AISettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
