"""Workflow for scheduled capacity mode changes."""

import logging
from datetime import timedelta, timezone

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..models.types import (
        NotificationSeverity,
        ScheduledCapacityChangeInput,
        ScheduledCapacityChangeResult,
    )
    from ..activities import (
        disable_provisioning,
        enable_provisioning,
        send_slack_notification,
        verify_namespace_capacity,
    )

logger = logging.getLogger(__name__)


@workflow.defn
class ScheduledCapacityChangeWorkflow:
    """Workflow that manages scheduled capacity mode changes for a namespace.

    This workflow:
    1. Immediately sets a namespace to a specific number of TRUs
    2. After 2 minutes, verifies the change was successful
    3. Sends Slack alert if verification fails
    4. If an end time was provided, sleeps until that time and reverts to on-demand
    5. Verifies the revert was successful and alerts if not
    """

    @workflow.run
    async def run(self, input: ScheduledCapacityChangeInput) -> ScheduledCapacityChangeResult:
        """Execute the scheduled capacity change workflow.

        Args:
            input: Workflow input parameters

        Returns:
            ScheduledCapacityChangeResult with status of all operations
        """
        workflow.logger.info(
            f"Starting scheduled capacity change workflow for {input.namespace}: "
            f"Set to {input.desired_trus} TRUs"
            + (f", revert at {input.end_time}" if input.end_time else "")
        )

        errors = []
        initial_change_success = False
        verification_success = False
        reverted_to_on_demand = False
        revert_verification_success = False

        # Step 1: Enable provisioning immediately
        workflow.logger.info(
            f"Step 1: Enabling provisioning for {input.namespace} "
            f"with {input.desired_trus} TRUs"
        )
        try:
            await workflow.execute_activity(
                enable_provisioning,
                args=[input.namespace, input.desired_trus],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=30),
                    maximum_attempts=3,
                    backoff_coefficient=2.0,
                ),
            )
            initial_change_success = True
            workflow.logger.info(
                f"Successfully enabled provisioning for {input.namespace}"
            )
        except Exception as e:
            error_msg = f"Failed to enable provisioning for {input.namespace}: {str(e)}"
            workflow.logger.error(error_msg)
            errors.append(error_msg)
            
            # Send critical notification
            try:
                await workflow.execute_activity(
                    send_slack_notification,
                    args=[f"❌ Scheduled capacity change failed for {input.namespace}: {error_msg}", NotificationSeverity.CRITICAL],
                    start_to_close_timeout=timedelta(seconds=30),
                )
            except Exception as notify_error:
                workflow.logger.error(f"Failed to send notification: {notify_error}")
            
            # Return early if initial change failed
            return ScheduledCapacityChangeResult(
                namespace=input.namespace,
                initial_change_success=False,
                verification_success=False,
                errors=errors,
            )

        # Step 2: Wait 2 minutes before verification
        workflow.logger.info("Step 2: Waiting 2 minutes before verification")
        await workflow.sleep(timedelta(minutes=2))

        # Step 3: Verify the change
        workflow.logger.info(
            f"Step 3: Verifying capacity for {input.namespace} "
            f"(expected provisioned mode with {input.desired_trus} TRUs)"
        )
        try:
            verification_success = await workflow.execute_activity(
                verify_namespace_capacity,
                args=[input.namespace, "provisioned", input.desired_trus],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=30),
                    maximum_attempts=3,
                    backoff_coefficient=2.0,
                ),
            )
            
            if verification_success:
                workflow.logger.info(
                    f"✓ Verification successful: {input.namespace} has "
                    f"{input.desired_trus} TRUs provisioned"
                )
            else:
                error_msg = (
                    f"Verification failed: {input.namespace} does not have "
                    f"the expected capacity ({input.desired_trus} TRUs)"
                )
                workflow.logger.error(error_msg)
                errors.append(error_msg)
                
                # Send error notification
                try:
                    await workflow.execute_activity(
                        send_slack_notification,
                        args=[
                            f"⚠️ Capacity verification failed for {input.namespace}: "
                            f"Expected {input.desired_trus} TRUs but verification did not pass. "
                            f"Please check the namespace manually.",
                            NotificationSeverity.ERROR
                        ],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                except Exception as notify_error:
                    workflow.logger.error(f"Failed to send notification: {notify_error}")
        except Exception as e:
            error_msg = f"Failed to verify capacity for {input.namespace}: {str(e)}"
            workflow.logger.error(error_msg)
            errors.append(error_msg)
            
            # Send error notification
            try:
                await workflow.execute_activity(
                    send_slack_notification,
                    args=[f"⚠️ Capacity verification error for {input.namespace}: {error_msg}", NotificationSeverity.ERROR],
                    start_to_close_timeout=timedelta(seconds=30),
                )
            except Exception as notify_error:
                workflow.logger.error(f"Failed to send notification: {notify_error}")

        # Step 4: If end_time provided and verification succeeded, sleep and revert
        if input.end_time and verification_success:
            workflow.logger.info(
                f"Step 4: End time provided ({input.end_time}), "
                f"calculating sleep duration"
            )
            
            # Calculate sleep duration
            current_time = workflow.now()
            if input.end_time > current_time:
                sleep_duration = input.end_time - current_time
                workflow.logger.info(
                    f"Sleeping for {sleep_duration} until end time ({input.end_time})"
                )
                await workflow.sleep(sleep_duration)
            else:
                workflow.logger.warning(
                    f"End time {input.end_time} is in the past "
                    f"(current time: {current_time}). Reverting immediately."
                )
            
            # Revert to on-demand
            workflow.logger.info(f"Step 5: Reverting {input.namespace} to on-demand")
            try:
                await workflow.execute_activity(
                    disable_provisioning,
                    args=[input.namespace],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=1),
                        maximum_interval=timedelta(seconds=30),
                        maximum_attempts=3,
                        backoff_coefficient=2.0,
                    ),
                )
                reverted_to_on_demand = True
                workflow.logger.info(
                    f"Successfully reverted {input.namespace} to on-demand"
                )
            except Exception as e:
                error_msg = f"Failed to revert {input.namespace} to on-demand: {str(e)}"
                workflow.logger.error(error_msg)
                errors.append(error_msg)
                
                # Send critical notification
                try:
                    await workflow.execute_activity(
                        send_slack_notification,
                        args=[f"❌ Failed to revert {input.namespace} to on-demand: {error_msg}", NotificationSeverity.CRITICAL],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                except Exception as notify_error:
                    workflow.logger.error(f"Failed to send notification: {notify_error}")
                
                # Return result with revert failure
                return ScheduledCapacityChangeResult(
                    namespace=input.namespace,
                    initial_change_success=initial_change_success,
                    verification_success=verification_success,
                    reverted_to_on_demand=False,
                    revert_verification_success=False,
                    errors=errors,
                )
            
            # Wait 2 minutes before verifying revert
            workflow.logger.info("Step 6: Waiting 2 minutes before verifying revert")
            await workflow.sleep(timedelta(minutes=2))
            
            # Verify the revert to on-demand
            workflow.logger.info(
                f"Step 7: Verifying {input.namespace} is back to on-demand"
            )
            try:
                revert_verification_success = await workflow.execute_activity(
                    verify_namespace_capacity,
                    args=[input.namespace, "on-demand", 0],  # TRUs not checked for on-demand mode
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=1),
                        maximum_interval=timedelta(seconds=30),
                        maximum_attempts=3,
                        backoff_coefficient=2.0,
                    ),
                )
                
                if revert_verification_success:
                    workflow.logger.info(
                        f"✓ Revert verification successful: {input.namespace} is on-demand"
                    )
                    
                    # Send success notification
                    try:
                        await workflow.execute_activity(
                            send_slack_notification,
                            args=[f"✅ Successfully reverted {input.namespace} to on-demand mode", NotificationSeverity.INFO],
                            start_to_close_timeout=timedelta(seconds=30),
                        )
                    except Exception as notify_error:
                        workflow.logger.error(f"Failed to send notification: {notify_error}")
                else:
                    error_msg = f"Revert verification failed: {input.namespace} is not in on-demand mode"
                    workflow.logger.error(error_msg)
                    errors.append(error_msg)
                    
                    # Send error notification
                    try:
                        await workflow.execute_activity(
                            send_slack_notification,
                            args=[
                                f"⚠️ Revert verification failed for {input.namespace}: "
                                f"Expected on-demand mode but verification did not pass. "
                                f"Please check the namespace manually.",
                                NotificationSeverity.ERROR
                            ],
                            start_to_close_timeout=timedelta(seconds=30),
                        )
                    except Exception as notify_error:
                        workflow.logger.error(f"Failed to send notification: {notify_error}")
                    
            except Exception as e:
                error_msg = f"Failed to verify revert for {input.namespace}: {str(e)}"
                workflow.logger.error(error_msg)
                errors.append(error_msg)
                
                # Send error notification
                try:
                    await workflow.execute_activity(
                        send_slack_notification,
                        args=[f"⚠️ Revert verification error for {input.namespace}: {error_msg}", NotificationSeverity.ERROR],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                except Exception as notify_error:
                    workflow.logger.error(f"Failed to send notification: {notify_error}")

        # Build and return result
        result = ScheduledCapacityChangeResult(
            namespace=input.namespace,
            initial_change_success=initial_change_success,
            verification_success=verification_success,
            reverted_to_on_demand=reverted_to_on_demand,
            revert_verification_success=revert_verification_success,
            errors=errors,
        )

        workflow.logger.info(f"Workflow completed: {result}")
        return result
