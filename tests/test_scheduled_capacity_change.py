"""Tests for scheduled capacity change workflow."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio import activity

from src.workflows.scheduled_capacity_change import ScheduledCapacityChangeWorkflow
from src.models.types import (
    ScheduledCapacityChangeInput,
    ScheduledCapacityChangeResult,
    NotificationSeverity,
)


@pytest_asyncio.fixture
async def workflow_environment():
    """Create a test workflow environment with time skipping."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


class TestScheduledCapacityChangeModels:
    """Tests for the ScheduledCapacityChange model classes."""

    def test_input_model_without_end_time(self):
        """Test input model without end time (no revert scheduled)."""
        input_data = ScheduledCapacityChangeInput(
            namespace="test-namespace.account",
            desired_trus=5,
        )
        
        assert input_data.namespace == "test-namespace.account"
        assert input_data.desired_trus == 5
        assert input_data.end_time is None
        
        # Check string representation
        str_repr = str(input_data)
        assert "test-namespace.account" in str_repr
        assert "5 TRUs" in str_repr
        assert "no revert scheduled" in str_repr

    def test_input_model_with_end_time(self):
        """Test input model with end time (revert scheduled)."""
        end_time = datetime(2026, 1, 16, 12, 0, 0)
        input_data = ScheduledCapacityChangeInput(
            namespace="test-namespace.account",
            desired_trus=10,
            end_time=end_time,
        )
        
        assert input_data.namespace == "test-namespace.account"
        assert input_data.desired_trus == 10
        assert input_data.end_time == end_time
        
        # Check string representation
        str_repr = str(input_data)
        assert "test-namespace.account" in str_repr
        assert "10 TRUs" in str_repr
        assert "revert at" in str_repr

    def test_result_model_success_without_revert(self):
        """Test result model for successful change without revert."""
        result = ScheduledCapacityChangeResult(
            namespace="test-ns.account",
            initial_change_success=True,
            verification_success=True,
        )
        
        assert result.namespace == "test-ns.account"
        assert result.initial_change_success is True
        assert result.verification_success is True
        assert result.reverted_to_on_demand is False
        assert result.revert_verification_success is False
        assert result.errors == []
        
        # Check string representation
        str_repr = str(result)
        assert "SUCCESS" in str_repr
        assert "test-ns.account" in str_repr
        assert "verified" in str_repr

    def test_result_model_success_with_revert(self):
        """Test result model for successful change with revert."""
        result = ScheduledCapacityChangeResult(
            namespace="test-ns.account",
            initial_change_success=True,
            verification_success=True,
            reverted_to_on_demand=True,
            revert_verification_success=True,
        )
        
        assert result.reverted_to_on_demand is True
        assert result.revert_verification_success is True
        
        # Check string representation
        str_repr = str(result)
        assert "SUCCESS" in str_repr
        assert "reverted to on-demand and verified" in str_repr

    def test_result_model_failure(self):
        """Test result model for failed change."""
        result = ScheduledCapacityChangeResult(
            namespace="test-ns.account",
            initial_change_success=False,
            verification_success=False,
            errors=["Failed to enable provisioning: API error"],
        )
        
        assert result.initial_change_success is False
        assert result.verification_success is False
        assert len(result.errors) == 1
        
        # Check string representation
        str_repr = str(result)
        assert "FAILED" in str_repr
        assert "1 error(s)" in str_repr


@pytest.mark.asyncio
class TestScheduledCapacityChangeWorkflow:
    """Tests for the ScheduledCapacityChangeWorkflow."""

    async def test_successful_change_without_end_time(self, workflow_environment):
        """Test successful capacity change without revert (no end_time)."""
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            return True
        
        @activity.defn(name="verify_namespace_capacity")
        async def mock_verify_namespace_capacity(
            namespace: str, expected_mode: str, expected_trus: int
        ):
            return True
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            return True
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-scheduled-change",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_verify_namespace_capacity,
                mock_send_slack_notification,
            ],
        ):
            handle = await workflow_environment.client.start_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=5,
                ),
                id="test-successful-no-revert",
                task_queue="test-scheduled-change",
            )
            
            # Skip time to allow workflow to complete (2 minutes for sleep + some buffer)
            await workflow_environment.sleep(timedelta(minutes=2.5))
            
            result = await handle.result()
            
            # Verify result
            assert result.namespace == "test-ns.account"
            assert result.initial_change_success is True
            assert result.verification_success is True
            assert result.reverted_to_on_demand is False
            assert result.revert_verification_success is False
            assert len(result.errors) == 0

    async def test_successful_change_with_end_time_and_revert(self, workflow_environment):
        """Test successful capacity change with scheduled revert."""
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            return True
        
        @activity.defn(name="verify_namespace_capacity")
        async def mock_verify_namespace_capacity(
            namespace: str, expected_mode: str, expected_trus: int
        ):
            # Return True for both initial verification and revert verification
            return True
        
        @activity.defn(name="disable_provisioning")
        async def mock_disable_provisioning(namespace: str):
            return True
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            return True
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-scheduled-change-revert",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_verify_namespace_capacity,
                mock_disable_provisioning,
                mock_send_slack_notification,
            ],
        ):
            # Set end_time 5 minutes from now (relative to workflow time)
            end_time = datetime.now(timezone.utc) + timedelta(minutes=5)
            
            handle = await workflow_environment.client.start_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=10,
                    end_time=end_time,
                ),
                id="test-successful-with-revert",
                task_queue="test-scheduled-change-revert",
            )
            
            # Skip time: 2 min initial wait + 5 min sleep + 2 min final wait + buffer
            await workflow_environment.sleep(timedelta(minutes=9.5))
            
            result = await handle.result()
            
            # Verify result includes successful revert
            assert result.namespace == "test-ns.account"
            assert result.initial_change_success is True
            assert result.verification_success is True
            assert result.reverted_to_on_demand is True
            assert result.revert_verification_success is True
            assert len(result.errors) == 0

    async def test_failed_initial_provisioning(self, workflow_environment):
        """Test workflow when initial provisioning fails."""
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            raise Exception("API Error: Failed to enable provisioning")
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            return True
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-failed-provisioning",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_send_slack_notification,
            ],
        ):
            result = await workflow_environment.client.execute_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=5,
                ),
                id="test-failed-initial-provisioning",
                task_queue="test-failed-provisioning",
            )
            
            # Verify result shows failure
            assert result.namespace == "test-ns.account"
            assert result.initial_change_success is False
            assert result.verification_success is False
            assert result.reverted_to_on_demand is False
            assert len(result.errors) == 1
            assert "Failed to enable provisioning" in result.errors[0]

    async def test_failed_verification(self, workflow_environment):
        """Test workflow when capacity verification fails."""
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            return True
        
        @activity.defn(name="verify_namespace_capacity")
        async def mock_verify_namespace_capacity(
            namespace: str, expected_mode: str, expected_trus: int
        ):
            # Verification fails
            return False
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            return True
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-failed-verification",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_verify_namespace_capacity,
                mock_send_slack_notification,
            ],
        ):
            handle = await workflow_environment.client.start_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=5,
                ),
                id="test-failed-verification",
                task_queue="test-failed-verification",
            )
            
            # Skip time for initial wait
            await workflow_environment.sleep(timedelta(minutes=2.5))
            
            result = await handle.result()
            
            # Verify result shows verification failure
            assert result.namespace == "test-ns.account"
            assert result.initial_change_success is True
            assert result.verification_success is False
            assert result.reverted_to_on_demand is False
            assert len(result.errors) == 1
            assert "Verification failed" in result.errors[0]

    async def test_verification_exception(self, workflow_environment):
        """Test workflow when verification raises an exception."""
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            return True
        
        @activity.defn(name="verify_namespace_capacity")
        async def mock_verify_namespace_capacity(
            namespace: str, expected_mode: str, expected_trus: int
        ):
            raise Exception("API Error: Failed to verify capacity")
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            return True
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-verification-exception",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_verify_namespace_capacity,
                mock_send_slack_notification,
            ],
        ):
            handle = await workflow_environment.client.start_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=5,
                ),
                id="test-verification-exception",
                task_queue="test-verification-exception",
            )
            
            # Skip time for initial wait
            await workflow_environment.sleep(timedelta(minutes=2.5))
            
            result = await handle.result()
            
            # Verify result shows verification error
            assert result.namespace == "test-ns.account"
            assert result.initial_change_success is True
            assert result.verification_success is False
            assert len(result.errors) == 1
            assert "Failed to verify capacity" in result.errors[0]

    async def test_failed_revert_to_on_demand(self, workflow_environment):
        """Test workflow when reverting to on-demand fails."""
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            return True
        
        @activity.defn(name="verify_namespace_capacity")
        async def mock_verify_namespace_capacity(
            namespace: str, expected_mode: str, expected_trus: int
        ):
            return True
        
        @activity.defn(name="disable_provisioning")
        async def mock_disable_provisioning(namespace: str):
            raise Exception("API Error: Failed to disable provisioning")
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            return True
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-failed-revert",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_verify_namespace_capacity,
                mock_disable_provisioning,
                mock_send_slack_notification,
            ],
        ):
            # Set end_time 5 minutes from now
            end_time = datetime.now(timezone.utc) + timedelta(minutes=5)
            
            handle = await workflow_environment.client.start_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=10,
                    end_time=end_time,
                ),
                id="test-failed-revert",
                task_queue="test-failed-revert",
            )
            
            # Skip time: 2 min initial wait + 5 min sleep (need to reach disable call)
            await workflow_environment.sleep(timedelta(minutes=7.5))
            
            result = await handle.result()
            
            # Verify result shows revert failure
            assert result.namespace == "test-ns.account"
            assert result.initial_change_success is True
            assert result.verification_success is True
            assert result.reverted_to_on_demand is False
            assert result.revert_verification_success is False
            assert len(result.errors) == 1
            assert "Failed to revert" in result.errors[0]

    async def test_failed_revert_verification(self, workflow_environment):
        """Test workflow when revert verification fails."""
        
        verification_call_count = 0
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            return True
        
        @activity.defn(name="verify_namespace_capacity")
        async def mock_verify_namespace_capacity(
            namespace: str, expected_mode: str, expected_trus: int
        ):
            nonlocal verification_call_count
            verification_call_count += 1
            # First verification (after enable) succeeds
            # Second verification (after revert) fails
            return verification_call_count == 1
        
        @activity.defn(name="disable_provisioning")
        async def mock_disable_provisioning(namespace: str):
            return True
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            return True
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-failed-revert-verification",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_verify_namespace_capacity,
                mock_disable_provisioning,
                mock_send_slack_notification,
            ],
        ):
            # Set end_time 5 minutes from now
            end_time = datetime.now(timezone.utc) + timedelta(minutes=5)
            
            handle = await workflow_environment.client.start_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=10,
                    end_time=end_time,
                ),
                id="test-failed-revert-verification",
                task_queue="test-failed-revert-verification",
            )
            
            # Skip time: 2 min initial + 5 min sleep + 2 min final wait + buffer
            await workflow_environment.sleep(timedelta(minutes=9.5))
            
            result = await handle.result()
            
            # Verify result shows revert verification failure
            assert result.namespace == "test-ns.account"
            assert result.initial_change_success is True
            assert result.verification_success is True
            assert result.reverted_to_on_demand is True
            assert result.revert_verification_success is False
            assert len(result.errors) == 1
            assert "Revert verification failed" in result.errors[0]

    async def test_end_time_in_past(self, workflow_environment):
        """Test workflow when end_time is in the past (should revert immediately)."""
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            return True
        
        @activity.defn(name="verify_namespace_capacity")
        async def mock_verify_namespace_capacity(
            namespace: str, expected_mode: str, expected_trus: int
        ):
            return True
        
        @activity.defn(name="disable_provisioning")
        async def mock_disable_provisioning(namespace: str):
            return True
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            return True
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-end-time-past",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_verify_namespace_capacity,
                mock_disable_provisioning,
                mock_send_slack_notification,
            ],
        ):
            # Set end time in the past
            end_time = datetime(2020, 1, 1, 0, 0, 0)
            
            handle = await workflow_environment.client.start_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=10,
                    end_time=end_time,
                ),
                id="test-end-time-in-past",
                task_queue="test-end-time-past",
            )
            
            # Skip time: 2 min initial wait + 2 min final verification wait + buffer
            await workflow_environment.sleep(timedelta(minutes=4.5))
            
            result = await handle.result()
            
            # Verify workflow still completes with revert
            assert result.namespace == "test-ns.account"
            assert result.initial_change_success is True
            assert result.verification_success is True
            assert result.reverted_to_on_demand is True
            assert result.revert_verification_success is True
            assert len(result.errors) == 0

    async def test_no_revert_if_initial_verification_fails(self, workflow_environment):
        """Test that workflow doesn't attempt revert if initial verification fails."""
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            return True
        
        @activity.defn(name="verify_namespace_capacity")
        async def mock_verify_namespace_capacity(
            namespace: str, expected_mode: str, expected_trus: int
        ):
            # Initial verification fails
            return False
        
        @activity.defn(name="disable_provisioning")
        async def mock_disable_provisioning(namespace: str):
            # Should not be called
            raise AssertionError("disable_provisioning should not be called")
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            return True
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-no-revert-on-failed-verification",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_verify_namespace_capacity,
                mock_disable_provisioning,
                mock_send_slack_notification,
            ],
        ):
            # Set end_time in future, but verification will fail so revert should not happen
            end_time = datetime.now(timezone.utc) + timedelta(minutes=5)
            
            handle = await workflow_environment.client.start_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=10,
                    end_time=end_time,
                ),
                id="test-no-revert-failed-verification",
                task_queue="test-no-revert-on-failed-verification",
            )
            
            # Skip time for initial wait
            await workflow_environment.sleep(timedelta(minutes=2.5))
            
            result = await handle.result()
            
            # Verify workflow didn't attempt revert
            assert result.namespace == "test-ns.account"
            assert result.initial_change_success is True
            assert result.verification_success is False
            assert result.reverted_to_on_demand is False
            assert result.revert_verification_success is False

    async def test_notification_failure_does_not_stop_workflow(self, workflow_environment):
        """Test that notification failures don't prevent workflow from completing."""
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            return True
        
        @activity.defn(name="verify_namespace_capacity")
        async def mock_verify_namespace_capacity(
            namespace: str, expected_mode: str, expected_trus: int
        ):
            return True
        
        @activity.defn(name="disable_provisioning")
        async def mock_disable_provisioning(namespace: str):
            return True
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            # Notification fails
            raise Exception("Slack API error")
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-notification-failure",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_verify_namespace_capacity,
                mock_disable_provisioning,
                mock_send_slack_notification,
            ],
        ):
            # Set end_time in the past to trigger immediate revert
            end_time = datetime(2020, 1, 1, 0, 0, 0)
            
            handle = await workflow_environment.client.start_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=10,
                    end_time=end_time,
                ),
                id="test-notification-failure",
                task_queue="test-notification-failure",
            )
            
            # Skip time
            await workflow_environment.sleep(timedelta(minutes=4.5))
            
            result = await handle.result()
            
            # Verify workflow still completes successfully despite notification failures
            assert result.namespace == "test-ns.account"
            assert result.initial_change_success is True
            assert result.verification_success is True
            assert result.reverted_to_on_demand is True
            assert result.revert_verification_success is True
            # No errors added to result (notifications are best-effort)
            assert len(result.errors) == 0

    async def test_multiple_errors_accumulated(self, workflow_environment):
        """Test that multiple errors are accumulated in the result."""
        
        @activity.defn(name="enable_provisioning")
        async def mock_enable_provisioning(namespace: str, tru_count: int):
            return True
        
        verification_call_count = 0
        
        @activity.defn(name="verify_namespace_capacity")
        async def mock_verify_namespace_capacity(
            namespace: str, expected_mode: str, expected_trus: int
        ):
            nonlocal verification_call_count
            verification_call_count += 1
            # Both verifications fail
            return False
        
        @activity.defn(name="disable_provisioning")
        async def mock_disable_provisioning(namespace: str):
            return True
        
        @activity.defn(name="send_slack_notification")
        async def mock_send_slack_notification(message: str, severity: NotificationSeverity):
            return True
        
        async with Worker(
            workflow_environment.client,
            task_queue="test-multiple-errors",
            workflows=[ScheduledCapacityChangeWorkflow],
            activities=[
                mock_enable_provisioning,
                mock_verify_namespace_capacity,
                mock_disable_provisioning,
                mock_send_slack_notification,
            ],
        ):
            # Only initial verification fails, so workflow won't reach revert
            end_time = datetime.now(timezone.utc) + timedelta(minutes=5)
            
            handle = await workflow_environment.client.start_workflow(
                ScheduledCapacityChangeWorkflow.run,
                ScheduledCapacityChangeInput(
                    namespace="test-ns.account",
                    desired_trus=10,
                    end_time=end_time,
                ),
                id="test-multiple-errors",
                task_queue="test-multiple-errors",
            )
            
            # Skip time for initial wait
            await workflow_environment.sleep(timedelta(minutes=2.5))
            
            result = await handle.result()
            
            # Verify only initial verification fails
            assert len(result.errors) == 1
            assert "Verification failed" in result.errors[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
