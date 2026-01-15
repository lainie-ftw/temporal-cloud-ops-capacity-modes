"""Configuration management for Temporal Cloud capacity automation."""

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # NOTE: Temporal connection settings (TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE, 
    # TEMPORAL_API_KEY, etc.) are now loaded via temporalio.envconfig.ClientConfig
    # See scripts for usage of ClientConfig.load_client_connect_config()

    # Cloud Ops API Settings
    temporal_cloud_ops_api_key: str = Field(
        ...,
        description="Temporal Cloud Ops API key for provisioning operations",
    )
    cloud_ops_api_base_url: str = Field(
        default="https://saas-api.tmprl.cloud",
        description="Base URL for Cloud Ops API",
    )

    # Cloud Metrics API Settings
    temporal_cloud_metrics_api_key: str = Field(
        ...,
        description="Temporal Cloud Metrics API key for reading metrics (Metrics Read-Only role)",
    )
    cloud_metrics_api_base_url: str = Field(
        default="https://metrics.temporal.io",
        description="Base URL for Cloud Metrics OpenMetrics API",
    )

    # Operational Settings
    dry_run_mode: bool = Field(
        default=False,
        description="If true, preview changes without executing them",
    )
    namespace_allowlist: list[str] = Field(
        default_factory=list,
        description="If specified, only manage these namespaces (comma-separated)",
    )
    namespace_denylist: list[str] = Field(
        default_factory=list,
        description="Namespaces to exclude from management (comma-separated)",
    )

    # Worker Settings
    task_queue: str = Field(
        default="capacity-management-task-queue",
        description="Task queue name for the worker",
    )

    @field_validator("namespace_allowlist", "namespace_denylist", mode="before")
    @classmethod
    def parse_comma_separated(cls, v):
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            return [ns.strip() for ns in v.split(",") if ns.strip()]
        return v or []

    def should_manage_namespace(self, namespace: str) -> bool:
        """Check if a namespace should be managed based on allow/deny lists."""
        # If allowlist is specified, namespace must be in it
        if self.namespace_allowlist and namespace not in self.namespace_allowlist:
            return False

        # If denylist is specified, namespace must not be in it
        if self.namespace_denylist and namespace in self.namespace_denylist:
            return False

        return True


# Global settings instance
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global settings
    if settings is None:
        settings = Settings()
    return settings
