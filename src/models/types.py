"""Type definitions for capacity management."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ProvisioningState(str, Enum):
    """Provisioning state for a namespace."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class NotificationSeverity(str, Enum):
    """Notification severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class NamespaceInfo:
    """Information about a namespace and its provisioning state."""

    namespace: str
    provisioning_state: ProvisioningState
    current_tru_count: Optional[int] = None
    region: Optional[str] = None

    def __str__(self) -> str:
        """String representation."""
        if self.current_tru_count is not None:
            return f"{self.namespace} ({self.provisioning_state.value}, {self.current_tru_count} TRUs)"
        return f"{self.namespace} ({self.provisioning_state.value})"


@dataclass
class NamespaceMetrics:
    """Metrics for a namespace to determine if action is needed."""

    namespace: str
    actions_per_hour: int
    is_throttled: bool
    throttle_percentage: float = 0.0

    def __str__(self) -> str:
        """String representation."""
        throttle_str = f", {self.throttle_percentage:.2f}% throttled" if self.is_throttled else ""
        return f"{self.namespace}: {self.actions_per_hour} actions/hour{throttle_str}"


@dataclass
class ActionDecision:
    """Decision about what action to take for a namespace."""

    namespace: str
    action: str  # "enable", "disable", or "none"
    reason: str
    current_state: ProvisioningState
    metrics: Optional[NamespaceMetrics] = None
    tru_count: Optional[int] = None

    def __str__(self) -> str:
        """String representation."""
        if self.action == "none":
            return f"[{self.namespace}] No action: {self.reason}"
        elif self.action == "enable":
            return f"[{self.namespace}] Enable with {self.tru_count} TRUs: {self.reason}"
        elif self.action == "disable":
            return f"[{self.namespace}] Disable: {self.reason}"
        return f"[{self.namespace}] {self.action}: {self.reason}"


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""

    total_namespaces_checked: int
    namespaces_enabled: list[str]
    namespaces_disabled: list[str]
    errors: list[str]
    decisions: list[ActionDecision]
    dry_run: bool = False

    def __str__(self) -> str:
        """String representation."""
        mode = "[DRY RUN] " if self.dry_run else ""
        enabled_str = f"Enabled: {len(self.namespaces_enabled)}"
        disabled_str = f"Disabled: {len(self.namespaces_disabled)}"
        error_str = f"Errors: {len(self.errors)}"
        return f"{mode}Checked {self.total_namespaces_checked} namespaces - {enabled_str}, {disabled_str}, {error_str}"


@dataclass
class NamespaceRecommendation:
    """Recommendation for a namespace with action metrics and TRU recommendation."""

    namespace: str
    action_limit: float
    action_count: float
    recommended_trus: int

    def __str__(self) -> str:
        """String representation."""
        return (
            f"{self.namespace}: APS limit={self.action_limit:.0f}, "
            f"Current APS={self.action_count:.0f}, Recommended TRUs={self.recommended_trus}"
        )
