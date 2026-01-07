"""Main workflow for capacity management."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..models.types import (
        ActionDecision,
        NotificationSeverity,
        ProvisioningState,
        WorkflowResult,
    )
    from ..activities import (
        check_throttling,
        disable_provisioning,
        enable_provisioning,
        list_namespaces,
        send_slack_notification,
    )

logger = logging.getLogger(__name__)


@dataclass
class CapacityManagementInput:
    """Input parameters for the capacity management workflow."""

    default_tru_count: int = 5
    min_actions_threshold: int = 100
    dry_run: bool = False


@workflow.defn
class CapacityManagementWorkflow:
    """Workflow that manages provisioned capacity for Temporal Cloud namespaces.

    This workflow:
    1. Checks namespaces with provisioning enabled and disables if underutilized
    2. Checks namespaces with provisioning disabled and enables if throttled
    3. Sends Slack notifications on failures
    """

    def __init__(self):
        """Initialize workflow state."""
        self._decisions: list[ActionDecision] = []
        self._manual_trigger_requested = False

    @workflow.run
    async def run(self, input: CapacityManagementInput) -> WorkflowResult:
        """Execute the capacity management workflow.

        Args:
            input: Workflow input parameters

        Returns:
            WorkflowResult with summary of actions taken
        """
        workflow.logger.info(
            f"Starting capacity management workflow "
            f"(dry_run={input.dry_run}, tru_count={input.default_tru_count}, "
            f"threshold={input.min_actions_threshold})"
        )

        namespaces_enabled = []
        namespaces_disabled = []
        errors = []
        self._decisions = []

        try:
            # Step 1: Get all namespaces
            workflow.logger.info("Step 1: Listing all namespaces")
            namespaces = await workflow.execute_activity(
                list_namespaces,
                start_to_close_timeout=timedelta(minutes=2),
            )
            workflow.logger.info(f"Found {len(namespaces)} namespaces to manage")

            # Step 2: Check for namespaces to turn OFF
            workflow.logger.info(
                "Step 2: Checking namespaces with provisioning enabled"
            )
            enabled_namespaces = [
                ns for ns in namespaces
                if ns.provisioning_state == ProvisioningState.ENABLED
            ]
            workflow.logger.info(
                f"Found {len(enabled_namespaces)} namespaces with provisioning enabled"
            )

            for ns in enabled_namespaces:
                try:
                    # Check if underutilized
                    metrics = await workflow.execute_activity(
                        check_throttling,
                        ns.namespace,
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=RetryPolicy(
                            initial_interval=timedelta(seconds=1),
                            maximum_interval=timedelta(seconds=30),
                            maximum_attempts=3,
                            backoff_coefficient=2.0,
                        ),
                    )

                    if metrics.actions_per_hour < input.min_actions_threshold:
                        # Should disable
                        decision = ActionDecision(
                            namespace=ns.namespace,
                            action="disable",
                            reason=f"Actions per hour ({metrics.actions_per_hour}) below threshold ({input.min_actions_threshold})",
                            current_state=ns.provisioning_state,
                            metrics=metrics,
                        )
                        self._decisions.append(decision)
                        workflow.logger.info(str(decision))

                        # Execute disable
                        await workflow.execute_activity(
                            disable_provisioning,
                            ns.namespace,
                            start_to_close_timeout=timedelta(minutes=5),
                            retry_policy=RetryPolicy(
                                initial_interval=timedelta(seconds=1),
                                maximum_interval=timedelta(seconds=30),
                                maximum_attempts=3,
                                backoff_coefficient=2.0,
                            ),
                        )
                        namespaces_disabled.append(ns.namespace)
                    else:
                        # No action needed
                        decision = ActionDecision(
                            namespace=ns.namespace,
                            action="none",
                            reason=f"Actions per hour ({metrics.actions_per_hour}) above threshold",
                            current_state=ns.provisioning_state,
                            metrics=metrics,
                        )
                        self._decisions.append(decision)
                        workflow.logger.info(str(decision))

                except Exception as e:
                    error_msg = f"Error checking {ns.namespace} for disable: {str(e)}"
                    workflow.logger.error(error_msg)
                    errors.append(error_msg)

                    # Send notification on failure
                    try:
                        await workflow.execute_activity(
                            send_slack_notification,
                            error_msg,
                            NotificationSeverity.ERROR,
                            start_to_close_timeout=timedelta(seconds=30),
                        )
                    except Exception as notify_error:
                        workflow.logger.error(f"Failed to send notification: {notify_error}")

            # Step 3: Check for namespaces to turn ON
            workflow.logger.info(
                "Step 3: Checking namespaces with provisioning disabled"
            )
            disabled_namespaces = [
                ns for ns in namespaces
                if ns.provisioning_state == ProvisioningState.DISABLED
            ]
            workflow.logger.info(
                f"Found {len(disabled_namespaces)} namespaces with provisioning disabled"
            )

            for ns in disabled_namespaces:
                try:
                    # Check if throttled
                    metrics = await workflow.execute_activity(
                        check_throttling,
                        ns.namespace,
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=RetryPolicy(
                            initial_interval=timedelta(seconds=1),
                            maximum_interval=timedelta(seconds=30),
                            maximum_attempts=3,
                            backoff_coefficient=2.0,
                        ),
                    )

                    if metrics.is_throttled:
                        # Should enable
                        decision = ActionDecision(
                            namespace=ns.namespace,
                            action="enable",
                            reason=f"Namespace is throttled ({metrics.throttle_percentage:.2f}%)",
                            current_state=ns.provisioning_state,
                            metrics=metrics,
                            tru_count=input.default_tru_count,
                        )
                        self._decisions.append(decision)
                        workflow.logger.info(str(decision))

                        # Execute enable
                        await workflow.execute_activity(
                            enable_provisioning,
                            ns.namespace,
                            input.default_tru_count,
                            start_to_close_timeout=timedelta(minutes=5),
                            retry_policy=RetryPolicy(
                                initial_interval=timedelta(seconds=1),
                                maximum_interval=timedelta(seconds=30),
                                maximum_attempts=3,
                                backoff_coefficient=2.0,
                            ),
                        )
                        namespaces_enabled.append(ns.namespace)
                    else:
                        # No action needed
                        decision = ActionDecision(
                            namespace=ns.namespace,
                            action="none",
                            reason="Not throttled",
                            current_state=ns.provisioning_state,
                            metrics=metrics,
                        )
                        self._decisions.append(decision)
                        workflow.logger.info(str(decision))

                except Exception as e:
                    error_msg = f"Error checking {ns.namespace} for enable: {str(e)}"
                    workflow.logger.error(error_msg)
                    errors.append(error_msg)

                    # Send notification on failure
                    try:
                        await workflow.execute_activity(
                            send_slack_notification,
                            error_msg,
                            NotificationSeverity.ERROR,
                            start_to_close_timeout=timedelta(seconds=30),
                        )
                    except Exception as notify_error:
                        workflow.logger.error(f"Failed to send notification: {notify_error}")

        except Exception as e:
            error_msg = f"Fatal error in workflow: {str(e)}"
            workflow.logger.error(error_msg)
            errors.append(error_msg)

            # Send critical notification
            try:
                await workflow.execute_activity(
                    send_slack_notification,
                    error_msg,
                    NotificationSeverity.CRITICAL,
                    start_to_close_timeout=timedelta(seconds=30),
                )
            except Exception as notify_error:
                workflow.logger.error(f"Failed to send notification: {notify_error}")

        # Build result
        result = WorkflowResult(
            total_namespaces_checked=len(namespaces) if 'namespaces' in locals() else 0,
            namespaces_enabled=namespaces_enabled,
            namespaces_disabled=namespaces_disabled,
            errors=errors,
            decisions=self._decisions,
            dry_run=input.dry_run,
        )

        workflow.logger.info(f"Workflow completed: {result}")
        return result

    @workflow.signal
    async def trigger_evaluation(self):
        """Signal to manually trigger an evaluation.

        This signal can be used to manually trigger the workflow outside
        of the schedule.
        """
        workflow.logger.info("Manual evaluation trigger received")
        self._manual_trigger_requested = True

    @workflow.query
    def preview_actions(self) -> list[ActionDecision]:
        """Query to preview what actions would be taken.

        Returns:
            List of ActionDecision objects showing what would happen
        """
        return self._decisions

    @workflow.query
    def get_status(self) -> str:
        """Query to get current workflow status.

        Returns:
            Status string
        """
        if self._decisions:
            enable_count = sum(1 for d in self._decisions if d.action == "enable")
            disable_count = sum(1 for d in self._decisions if d.action == "disable")
            return f"Processed {len(self._decisions)} namespaces: {enable_count} to enable, {disable_count} to disable"
        return "No decisions made yet"
