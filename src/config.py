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

    # Temporal Connection Settings
    temporal_address: str = Field(
        ...,
        description="Temporal Cloud address (e.g., namespace.account.tmprl.cloud:7233)",
    )
    temporal_namespace: str = Field(
        ...,
        description="Temporal namespace to run this workflow in",
    )
    
    # Authentication - Use either API key OR mTLS certificates
    temporal_api_key: Optional[str] = Field(
        default=None,
        description="Temporal namespace API key (alternative to mTLS)",
    )
    temporal_cert_path: Optional[Path] = Field(
        default=None,
        description="Path to mTLS certificate file (alternative to API key)",
    )
    temporal_key_path: Optional[Path] = Field(
        default=None,
        description="Path to mTLS private key file (alternative to API key)",
    )

    # Cloud Ops API Settings
    temporal_cloud_ops_api_key: str = Field(
        ...,
        description="Temporal Cloud Ops API key for provisioning operations",
    )
    cloud_ops_api_base_url: str = Field(
        default="https://saas-api.tmprl.cloud",
        description="Base URL for Cloud Ops API",
    )

    # Capacity Management Settings
    default_tru_count: int = Field(
        default=5,
        gt=0,
        description="Number of TRUs to enable when turning on provisioned capacity",
    )
    min_actions_threshold: int = Field(
        default=100,
        ge=0,
        description="Minimum actions per hour to keep provisioned capacity enabled",
    )

    # Notification Settings
    slack_webhook_url: Optional[str] = Field(
        default=None,
        description="Slack webhook URL for failure notifications",
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

    @field_validator("temporal_cert_path", "temporal_key_path")
    @classmethod
    def validate_path_exists(cls, v):
        """Validate that certificate/key paths exist if provided."""
        if v is not None and not v.exists():
            raise ValueError(f"File not found: {v}")
        return v

    def validate_auth_config(self) -> None:
        """Validate that at least one authentication method is configured."""
        has_api_key = self.temporal_api_key is not None
        has_mtls = (
            self.temporal_cert_path is not None
            and self.temporal_key_path is not None
        )
        
        if not has_api_key and not has_mtls:
            raise ValueError(
                "Must provide either TEMPORAL_API_KEY or both "
                "TEMPORAL_CERT_PATH and TEMPORAL_KEY_PATH"
            )
        
        if has_mtls and (self.temporal_cert_path is None or self.temporal_key_path is None):
            raise ValueError(
                "If using mTLS, both TEMPORAL_CERT_PATH and "
                "TEMPORAL_KEY_PATH must be provided"
            )

    def use_api_key_auth(self) -> bool:
        """Check if using API key authentication."""
        return self.temporal_api_key is not None

    def use_mtls_auth(self) -> bool:
        """Check if using mTLS authentication."""
        return (
            self.temporal_cert_path is not None
            and self.temporal_key_path is not None
        )

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
