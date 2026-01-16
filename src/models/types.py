"""Type definitions for capacity management."""

from dataclasses import dataclass
from datetime import datetime, timezone
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
class NamespaceRecommendation:
    """Recommendation for a namespace with action metrics and TRU recommendation."""

    namespace: str
    action_limit: float
    action_count: float
    recommended_trus: int
    current_capacity_mode: str  # "provisioned" or "on-demand"
    current_trus: Optional[int]  # Current TRU count if provisioned
    recommended_capacity_mode: str  # "provisioned" or "on-demand"

    def __str__(self) -> str:
        """String representation."""
        current_tru_str = f"({self.current_trus} TRUs)" if self.current_trus else ""
        recommended_tru_str = f"({self.recommended_trus} TRUs)" if self.recommended_capacity_mode == "provisioned" else ""
        
        return (
            f"{self.namespace}: "
            f"Current Mode: {self.current_capacity_mode}{current_tru_str}, "
            f"Recommended Mode: {self.recommended_capacity_mode}{recommended_tru_str}, "
            f"APS limit: {self.action_limit:.0f}, Current APS: {self.action_count:.0f}"
        )


@dataclass
class ScheduledCapacityChangeInput:
    """Input parameters for scheduled capacity change workflow."""

    namespace: str
    desired_trus: int
    end_time: Optional[datetime] = None  # When to revert to on-demand (if provided)

    def __post_init__(self):
        """Ensure end_time is timezone-aware."""
        if self.end_time is not None and self.end_time.tzinfo is None:
            # Convert naive datetime to UTC-aware datetime
            self.end_time = self.end_time.replace(tzinfo=timezone.utc)

    def __str__(self) -> str:
        """String representation."""
        end_str = f", revert at {self.end_time}" if self.end_time else ", no revert scheduled"
        return f"Set {self.namespace} to {self.desired_trus} TRUs{end_str}"


@dataclass
class ScheduledCapacityChangeResult:
    """Result of scheduled capacity change workflow execution."""

    namespace: str
    initial_change_success: bool
    verification_success: bool
    reverted_to_on_demand: bool = False  # True if end_time was provided and revert attempted
    revert_verification_success: bool = False  # True if revert was verified successfully
    errors: list[str] = None

    def __post_init__(self):
        """Initialize errors list if None."""
        if self.errors is None:
            self.errors = []

    def __str__(self) -> str:
        """String representation."""
        status = "SUCCESS" if self.initial_change_success and self.verification_success else "FAILED"
        result = f"[{status}] {self.namespace}: "
        
        if self.initial_change_success:
            result += "provisioning enabled"
            if self.verification_success:
                result += " and verified"
            else:
                result += " but verification failed"
        else:
            result += "failed to enable provisioning"
        
        if self.reverted_to_on_demand:
            if self.revert_verification_success:
                result += ", reverted to on-demand and verified"
            else:
                result += ", reverted to on-demand but verification failed"
        
        if self.errors:
            result += f", {len(self.errors)} error(s)"
        
        return result
