"""Tests for capacity management workflow."""

import pytest
from datetime import timedelta

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.workflows.capacity_management import (
    CapacityManagementWorkflow,
    CapacityManagementInput,
)
from src.models.types import (
    NamespaceInfo,
    NamespaceMetrics,
    ProvisioningState,
)


@pytest.fixture
async def workflow_environment():
    """Create a test workflow environment."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


@pytest.mark.asyncio
async def test_workflow_dry_run(workflow_environment):
    """Test workflow in dry run mode."""
    
    # Mock activities that return test data
    async def mock_list_namespaces():
        return [
            NamespaceInfo(
                namespace="test-ns-1",
                provisioning_state=ProvisioningState.ENABLED,
                current_tru_count=5,
            ),
            NamespaceInfo(
                namespace="test-ns-2",
                provisioning_state=ProvisioningState.DISABLED,
            ),
        ]
    
    async def mock_check_throttling(namespace: str):
        if namespace == "test-ns-1":
            # Low usage - should be disabled
            return NamespaceMetrics(
                namespace=namespace,
                actions_per_hour=50,
                is_throttled=False,
            )
        else:
            # Throttled - should be enabled
            return NamespaceMetrics(
                namespace=namespace,
                actions_per_hour=1000,
                is_throttled=True,
                throttle_percentage=15.0,
            )
    
    async def mock_enable_provisioning(namespace: str, tru_count: int):
        return True
    
    async def mock_disable_provisioning(namespace: str):
        return True
    
    async def mock_send_slack_notification(message: str, severity):
        return True
    
    # Create worker with mocked activities
    async with Worker(
        workflow_environment.client,
        task_queue="test-task-queue",
        workflows=[CapacityManagementWorkflow],
        activities=[
            mock_list_namespaces,
            mock_check_throttling,
            mock_enable_provisioning,
            mock_disable_provisioning,
            mock_send_slack_notification,
        ],
    ):
        # Execute workflow
        result = await workflow_environment.client.execute_workflow(
            CapacityManagementWorkflow.run,
            CapacityManagementInput(
                default_tru_count=5,
                min_actions_threshold=100,
                dry_run=True,
            ),
            id="test-workflow",
            task_queue="test-task-queue",
        )
        
        # Verify results
        assert result.total_namespaces_checked == 2
        assert result.dry_run is True
        assert len(result.decisions) == 2


@pytest.mark.asyncio
async def test_workflow_decisions(workflow_environment):
    """Test that workflow makes correct decisions."""
    
    async def mock_list_namespaces():
        return [
            NamespaceInfo(
                namespace="high-usage",
                provisioning_state=ProvisioningState.ENABLED,
                current_tru_count=5,
            ),
            NamespaceInfo(
                namespace="low-usage",
                provisioning_state=ProvisioningState.ENABLED,
                current_tru_count=5,
            ),
        ]
    
    async def mock_check_throttling(namespace: str):
        if namespace == "high-usage":
            return NamespaceMetrics(
                namespace=namespace,
                actions_per_hour=500,  # Above threshold
                is_throttled=False,
            )
        else:
            return NamespaceMetrics(
                namespace=namespace,
                actions_per_hour=50,  # Below threshold
                is_throttled=False,
            )
    
    async def mock_enable_provisioning(namespace: str, tru_count: int):
        return True
    
    async def mock_disable_provisioning(namespace: str):
        return True
    
    async def mock_send_slack_notification(message: str, severity):
        return True
    
    async with Worker(
        workflow_environment.client,
        task_queue="test-task-queue",
        workflows=[CapacityManagementWorkflow],
        activities=[
            mock_list_namespaces,
            mock_check_throttling,
            mock_enable_provisioning,
            mock_disable_provisioning,
            mock_send_slack_notification,
        ],
    ):
        result = await workflow_environment.client.execute_workflow(
            CapacityManagementWorkflow.run,
            CapacityManagementInput(
                default_tru_count=5,
                min_actions_threshold=100,
                dry_run=True,
            ),
            id="test-workflow-decisions",
            task_queue="test-task-queue",
        )
        
        # Verify decisions
        assert len(result.decisions) == 2
        
        # Find decisions for each namespace
        high_usage_decision = next(d for d in result.decisions if d.namespace == "high-usage")
        low_usage_decision = next(d for d in result.decisions if d.namespace == "low-usage")
        
        # High usage should have no action
        assert high_usage_decision.action == "none"
        
        # Low usage should be disabled
        assert low_usage_decision.action == "disable"


def test_namespace_info_model():
    """Test NamespaceInfo model."""
    ns = NamespaceInfo(
        namespace="test",
        provisioning_state=ProvisioningState.ENABLED,
        current_tru_count=5,
    )
    
    assert ns.namespace == "test"
    assert ns.provisioning_state == ProvisioningState.ENABLED
    assert ns.current_tru_count == 5
    assert "test" in str(ns)
    assert "5 TRUs" in str(ns)


def test_namespace_metrics_model():
    """Test NamespaceMetrics model."""
    metrics = NamespaceMetrics(
        namespace="test",
        actions_per_hour=150,
        is_throttled=True,
        throttle_percentage=10.5,
    )
    
    assert metrics.namespace == "test"
    assert metrics.actions_per_hour == 150
    assert metrics.is_throttled is True
    assert metrics.throttle_percentage == 10.5
    assert "150 actions/hour" in str(metrics)
    assert "10.50% throttled" in str(metrics)
