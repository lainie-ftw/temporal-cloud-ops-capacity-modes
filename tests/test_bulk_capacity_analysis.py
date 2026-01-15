"""Tests for bulk capacity analysis workflow and activities."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta

from temporalio.testing import WorkflowEnvironment, ActivityEnvironment
from temporalio.worker import Worker
from temporalio import activity

from src.workflows.bulk_capacity_analysis import BulkCapacityAnalysisWorkflow
from src.activities.namespace_ops import get_all_namespace_metrics
from src.models.types import (
    NamespaceRecommendation,
    NamespaceInfo,
    ProvisioningState,
)


class TestNamespaceRecommendationModel:
    """Tests for the NamespaceRecommendation model."""

    def test_on_demand_recommendation(self):
        """Test on-demand namespace recommendation."""
        rec = NamespaceRecommendation(
            namespace="test-ns",
            action_limit=500.0,
            action_count=250.0,
            recommended_trus=0,
            current_capacity_mode="on-demand",
            current_trus=None,
            recommended_capacity_mode="on-demand",
        )
        
        assert rec.namespace == "test-ns"
        assert rec.current_capacity_mode == "on-demand"
        assert rec.current_trus is None
        assert rec.recommended_capacity_mode == "on-demand"
        assert rec.recommended_trus == 0
        
        # Check string representation
        str_repr = str(rec)
        assert "test-ns" in str_repr
        assert "on-demand" in str_repr
        assert "N/A" in str_repr

    def test_provisioned_recommendation(self):
        """Test provisioned namespace recommendation."""
        rec = NamespaceRecommendation(
            namespace="test-ns-heavy",
            action_limit=2500.0,
            action_count=2000.0,
            recommended_trus=5,
            current_capacity_mode="provisioned",
            current_trus=4,
            recommended_capacity_mode="provisioned",
        )
        
        assert rec.namespace == "test-ns-heavy"
        assert rec.current_capacity_mode == "provisioned"
        assert rec.current_trus == 4
        assert rec.recommended_capacity_mode == "provisioned"
        assert rec.recommended_trus == 5
        
        # Check string representation
        str_repr = str(rec)
        assert "test-ns-heavy" in str_repr
        assert "provisioned" in str_repr
        assert "4 TRUs" in str_repr
        assert "5 TRUs" in str_repr

    def test_scale_down_recommendation(self):
        """Test recommendation to scale down from provisioned to on-demand."""
        rec = NamespaceRecommendation(
            namespace="test-ns-light",
            action_limit=1500.0,
            action_count=100.0,
            recommended_trus=0,
            current_capacity_mode="provisioned",
            current_trus=3,
            recommended_capacity_mode="on-demand",
        )
        
        assert rec.current_capacity_mode == "provisioned"
        assert rec.recommended_capacity_mode == "on-demand"
        assert rec.current_trus == 3
        assert rec.recommended_trus == 0


@pytest.mark.asyncio
class TestGetAllNamespaceMetricsActivity:
    """Tests for the get_all_namespace_metrics activity."""

    async def test_activity_with_mocked_apis(self):
        """Test activity with mocked API responses."""
        # Mock the OpenMetrics client
        mock_metrics_data = {
            "namespace1.account": {
                "action_limit": 500.0,
                "action_count": 250.0,
            },
            "namespace2.account": {
                "action_limit": 1500.0,
                "action_count": 1200.0,
            },
        }
        
        # Mock the Cloud Ops namespace info
        def create_mock_namespace_info(namespace: str):
            if namespace == "namespace1.account":
                return NamespaceInfo(
                    namespace=namespace,
                    provisioning_state=ProvisioningState.DISABLED,
                    current_tru_count=None,
                )
            else:
                return NamespaceInfo(
                    namespace=namespace,
                    provisioning_state=ProvisioningState.ENABLED,
                    current_tru_count=3,
                )
        
        with patch("src.activities.namespace_ops.OpenMetricsClient") as MockMetricsClient, \
             patch("src.activities.namespace_ops.CloudOpsClient") as MockCloudOpsClient, \
             patch("src.activities.namespace_ops.get_settings") as mock_settings:
            
            # Setup mocks (use MagicMock for settings since it has sync methods)
            mock_settings_instance = MagicMock()
            mock_settings_instance.should_manage_namespace.return_value = True
            mock_settings_instance.temporal_cloud_metrics_api_key = "test-metrics-key"
            mock_settings_instance.cloud_metrics_api_base_url = "https://test-metrics.com"
            mock_settings_instance.temporal_cloud_ops_api_key = "test-ops-key"
            mock_settings_instance.cloud_ops_api_base_url = "https://test-ops.com"
            mock_settings.return_value = mock_settings_instance
            
            # Setup metrics client mock
            metrics_client_instance = AsyncMock()
            metrics_client_instance.get_all_namespace_metrics.return_value = mock_metrics_data
            metrics_client_instance.close = AsyncMock()
            MockMetricsClient.return_value = metrics_client_instance
            
            # Setup cloud ops client mock
            cloud_ops_client_instance = AsyncMock()
            cloud_ops_client_instance.get_namespace_info.side_effect = create_mock_namespace_info
            cloud_ops_client_instance.close = AsyncMock()
            MockCloudOpsClient.return_value = cloud_ops_client_instance
            
            # Run activity in test environment
            env = ActivityEnvironment()
            heartbeats = []
            env.on_heartbeat = lambda *args: heartbeats.append(args[0] if args else None)
            
            result = await env.run(get_all_namespace_metrics)
            
            # Verify results
            assert len(result) == 2
            
            # Check namespace1 (on-demand)
            ns1 = next(r for r in result if r.namespace == "namespace1.account")
            assert ns1.current_capacity_mode == "on-demand"
            assert ns1.current_trus is None
            assert ns1.recommended_capacity_mode == "on-demand"
            assert ns1.recommended_trus == 0
            assert ns1.action_limit == 500.0
            assert ns1.action_count == 250.0
            
            # Check namespace2 (provisioned)
            ns2 = next(r for r in result if r.namespace == "namespace2.account")
            assert ns2.current_capacity_mode == "provisioned"
            assert ns2.current_trus == 3
            assert ns2.recommended_capacity_mode == "provisioned"
            # With 1200 APS out of 1500 (80% utilization), should scale up to 4 TRUs
            assert ns2.recommended_trus == 4
            assert ns2.action_limit == 1500.0
            assert ns2.action_count == 1200.0
            
            # Verify API clients were closed
            metrics_client_instance.close.assert_called_once()
            cloud_ops_client_instance.close.assert_called_once()

    async def test_activity_handles_cloud_ops_errors(self):
        """Test that activity handles Cloud Ops API errors gracefully."""
        mock_metrics_data = {
            "namespace1.account": {
                "action_limit": 500.0,
                "action_count": 250.0,
            },
        }
        
        with patch("src.activities.namespace_ops.OpenMetricsClient") as MockMetricsClient, \
             patch("src.activities.namespace_ops.CloudOpsClient") as MockCloudOpsClient, \
             patch("src.activities.namespace_ops.get_settings") as mock_settings:
            
            # Setup mocks
            mock_settings_instance = MagicMock()
            mock_settings_instance.should_manage_namespace.return_value = True
            mock_settings_instance.temporal_cloud_metrics_api_key = "test-key"
            mock_settings_instance.cloud_metrics_api_base_url = "https://test.com"
            mock_settings_instance.temporal_cloud_ops_api_key = "test-key"
            mock_settings_instance.cloud_ops_api_base_url = "https://test.com"
            mock_settings.return_value = mock_settings_instance
            
            metrics_client_instance = AsyncMock()
            metrics_client_instance.get_all_namespace_metrics.return_value = mock_metrics_data
            metrics_client_instance.close = AsyncMock()
            MockMetricsClient.return_value = metrics_client_instance
            
            # Cloud Ops client raises exception
            cloud_ops_client_instance = AsyncMock()
            cloud_ops_client_instance.get_namespace_info.side_effect = Exception("API Error")
            cloud_ops_client_instance.close = AsyncMock()
            MockCloudOpsClient.return_value = cloud_ops_client_instance
            
            env = ActivityEnvironment()
            result = await env.run(get_all_namespace_metrics)
            
            # Activity should still return results with defaults
            assert len(result) == 1
            assert result[0].current_capacity_mode == "on-demand"
            assert result[0].current_trus is None


@pytest.mark.asyncio
class TestCapacityModeRecommendationLogic:
    """Tests that verify capacity mode recommendation logic based on metrics."""

    async def test_transition_from_on_demand_to_provisioned(self):
        """Test recommending transition from on-demand to provisioned when APS exceeds base capacity."""
        # Scenario: Currently on-demand, but needs more than 500 APS
        mock_metrics_data = {
            "heavy-namespace.account": {
                "action_limit": 500.0,  # Base capacity (on-demand or 1 TRU)
                "action_count": 1200.0,  # Needs more capacity
            },
        }
        
        def create_mock_namespace_info(namespace: str):
            return NamespaceInfo(
                namespace=namespace,
                provisioning_state=ProvisioningState.DISABLED,  # Currently on-demand
                current_tru_count=None,
            )
        
        with patch("src.activities.namespace_ops.OpenMetricsClient") as MockMetricsClient, \
             patch("src.activities.namespace_ops.CloudOpsClient") as MockCloudOpsClient, \
             patch("src.activities.namespace_ops.get_settings") as mock_settings:
            
            mock_settings_instance = MagicMock()
            mock_settings_instance.should_manage_namespace.return_value = True
            mock_settings_instance.temporal_cloud_metrics_api_key = "test-key"
            mock_settings_instance.cloud_metrics_api_base_url = "https://test.com"
            mock_settings_instance.temporal_cloud_ops_api_key = "test-key"
            mock_settings_instance.cloud_ops_api_base_url = "https://test.com"
            mock_settings.return_value = mock_settings_instance
            
            metrics_client_instance = AsyncMock()
            metrics_client_instance.get_all_namespace_metrics.return_value = mock_metrics_data
            metrics_client_instance.close = AsyncMock()
            MockMetricsClient.return_value = metrics_client_instance
            
            cloud_ops_client_instance = AsyncMock()
            cloud_ops_client_instance.get_namespace_info.side_effect = create_mock_namespace_info
            cloud_ops_client_instance.close = AsyncMock()
            MockCloudOpsClient.return_value = cloud_ops_client_instance
            
            env = ActivityEnvironment()
            result = await env.run(get_all_namespace_metrics)
            
            assert len(result) == 1
            ns = result[0]
            
            # Verify current state is on-demand
            assert ns.current_capacity_mode == "on-demand"
            assert ns.current_trus is None
            
            # Verify recommendation to switch to provisioned
            assert ns.recommended_capacity_mode == "provisioned"
            # 1200 APS needs 3 TRUs (ceil(1200/500) = 3)
            assert ns.recommended_trus == 3

    async def test_stay_on_demand_low_usage(self):
        """Test staying on-demand when usage is low."""
        mock_metrics_data = {
            "light-namespace.account": {
                "action_limit": 500.0,
                "action_count": 150.0,  # Well under base capacity
            },
        }
        
        def create_mock_namespace_info(namespace: str):
            return NamespaceInfo(
                namespace=namespace,
                provisioning_state=ProvisioningState.DISABLED,
                current_tru_count=None,
            )
        
        with patch("src.activities.namespace_ops.OpenMetricsClient") as MockMetricsClient, \
             patch("src.activities.namespace_ops.CloudOpsClient") as MockCloudOpsClient, \
             patch("src.activities.namespace_ops.get_settings") as mock_settings:
            
            mock_settings_instance = MagicMock()
            mock_settings_instance.should_manage_namespace.return_value = True
            mock_settings_instance.temporal_cloud_metrics_api_key = "test-key"
            mock_settings_instance.cloud_metrics_api_base_url = "https://test.com"
            mock_settings_instance.temporal_cloud_ops_api_key = "test-key"
            mock_settings_instance.cloud_ops_api_base_url = "https://test.com"
            mock_settings.return_value = mock_settings_instance
            
            metrics_client_instance = AsyncMock()
            metrics_client_instance.get_all_namespace_metrics.return_value = mock_metrics_data
            metrics_client_instance.close = AsyncMock()
            MockMetricsClient.return_value = metrics_client_instance
            
            cloud_ops_client_instance = AsyncMock()
            cloud_ops_client_instance.get_namespace_info.side_effect = create_mock_namespace_info
            cloud_ops_client_instance.close = AsyncMock()
            MockCloudOpsClient.return_value = cloud_ops_client_instance
            
            env = ActivityEnvironment()
            result = await env.run(get_all_namespace_metrics)
            
            assert len(result) == 1
            ns = result[0]
            
            # Verify current and recommended state both on-demand
            assert ns.current_capacity_mode == "on-demand"
            assert ns.recommended_capacity_mode == "on-demand"
            assert ns.recommended_trus == 0

    async def test_transition_from_provisioned_to_on_demand(self):
        """Test recommending scale-down from provisioned to on-demand when usage drops."""
        # Scenario: Currently provisioned with 5 TRUs, but only using 200 APS
        mock_metrics_data = {
            "scaling-down-namespace.account": {
                "action_limit": 2500.0,  # 5 TRUs
                "action_count": 200.0,    # Very low usage
            },
        }
        
        def create_mock_namespace_info(namespace: str):
            return NamespaceInfo(
                namespace=namespace,
                provisioning_state=ProvisioningState.ENABLED,
                current_tru_count=5,
            )
        
        with patch("src.activities.namespace_ops.OpenMetricsClient") as MockMetricsClient, \
             patch("src.activities.namespace_ops.CloudOpsClient") as MockCloudOpsClient, \
             patch("src.activities.namespace_ops.get_settings") as mock_settings:
            
            mock_settings_instance = MagicMock()
            mock_settings_instance.should_manage_namespace.return_value = True
            mock_settings_instance.temporal_cloud_metrics_api_key = "test-key"
            mock_settings_instance.cloud_metrics_api_base_url = "https://test.com"
            mock_settings_instance.temporal_cloud_ops_api_key = "test-key"
            mock_settings_instance.cloud_ops_api_base_url = "https://test.com"
            mock_settings.return_value = mock_settings_instance
            
            metrics_client_instance = AsyncMock()
            metrics_client_instance.get_all_namespace_metrics.return_value = mock_metrics_data
            metrics_client_instance.close = AsyncMock()
            MockMetricsClient.return_value = metrics_client_instance
            
            cloud_ops_client_instance = AsyncMock()
            cloud_ops_client_instance.get_namespace_info.side_effect = create_mock_namespace_info
            cloud_ops_client_instance.close = AsyncMock()
            MockCloudOpsClient.return_value = cloud_ops_client_instance
            
            env = ActivityEnvironment()
            result = await env.run(get_all_namespace_metrics)
            
            assert len(result) == 1
            ns = result[0]
            
            # Verify current state is provisioned
            assert ns.current_capacity_mode == "provisioned"
            assert ns.current_trus == 5
            
            # Verify recommendation to scale down to on-demand
            assert ns.recommended_capacity_mode == "on-demand"
            assert ns.recommended_trus == 0

    async def test_stay_provisioned_adjust_trus(self):
        """Test staying provisioned but adjusting TRU count based on usage."""
        # Scenario: Currently 3 TRUs, at 80% utilization, should scale up to 4
        mock_metrics_data = {
            "stable-namespace.account": {
                "action_limit": 1500.0,  # 3 TRUs
                "action_count": 1200.0,  # 80% utilization
            },
        }
        
        def create_mock_namespace_info(namespace: str):
            return NamespaceInfo(
                namespace=namespace,
                provisioning_state=ProvisioningState.ENABLED,
                current_tru_count=3,
            )
        
        with patch("src.activities.namespace_ops.OpenMetricsClient") as MockMetricsClient, \
             patch("src.activities.namespace_ops.CloudOpsClient") as MockCloudOpsClient, \
             patch("src.activities.namespace_ops.get_settings") as mock_settings:
            
            mock_settings_instance = MagicMock()
            mock_settings_instance.should_manage_namespace.return_value = True
            mock_settings_instance.temporal_cloud_metrics_api_key = "test-key"
            mock_settings_instance.cloud_metrics_api_base_url = "https://test.com"
            mock_settings_instance.temporal_cloud_ops_api_key = "test-key"
            mock_settings_instance.cloud_ops_api_base_url = "https://test.com"
            mock_settings.return_value = mock_settings_instance
            
            metrics_client_instance = AsyncMock()
            metrics_client_instance.get_all_namespace_metrics.return_value = mock_metrics_data
            metrics_client_instance.close = AsyncMock()
            MockMetricsClient.return_value = metrics_client_instance
            
            cloud_ops_client_instance = AsyncMock()
            cloud_ops_client_instance.get_namespace_info.side_effect = create_mock_namespace_info
            cloud_ops_client_instance.close = AsyncMock()
            MockCloudOpsClient.return_value = cloud_ops_client_instance
            
            env = ActivityEnvironment()
            result = await env.run(get_all_namespace_metrics)
            
            assert len(result) == 1
            ns = result[0]
            
            # Verify stays provisioned but scales up
            assert ns.current_capacity_mode == "provisioned"
            assert ns.current_trus == 3
            assert ns.recommended_capacity_mode == "provisioned"
            assert ns.recommended_trus == 4  # Scale up due to 80% utilization


@pytest.mark.asyncio
class TestBulkCapacityAnalysisWorkflow:
    """Tests for the BulkCapacityAnalysisWorkflow."""

    async def test_workflow_execution(self):
        """Test workflow execution with mock activity."""
        @activity.defn(name="get_all_namespace_metrics")
        async def mock_get_all_namespace_metrics():
            return [
                NamespaceRecommendation(
                    namespace="ns1.account",
                    action_limit=500.0,
                    action_count=200.0,
                    recommended_trus=0,
                    current_capacity_mode="on-demand",
                    current_trus=None,
                    recommended_capacity_mode="on-demand",
                ),
                NamespaceRecommendation(
                    namespace="ns2.account",
                    action_limit=2500.0,
                    action_count=2000.0,
                    recommended_trus=5,
                    current_capacity_mode="provisioned",
                    current_trus=4,
                    recommended_capacity_mode="provisioned",
                ),
            ]
        
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-bulk-analysis",
                workflows=[BulkCapacityAnalysisWorkflow],
                activities=[mock_get_all_namespace_metrics],
            ):
                result = await env.client.execute_workflow(
                    BulkCapacityAnalysisWorkflow.run,
                    id="test-bulk-analysis-workflow",
                    task_queue="test-bulk-analysis",
                )
                
                # Verify results
                assert len(result) == 2
                assert result[0].namespace == "ns1.account"
                assert result[0].current_capacity_mode == "on-demand"
                assert result[1].namespace == "ns2.account"
                assert result[1].current_capacity_mode == "provisioned"
                assert result[1].recommended_trus == 5

    async def test_workflow_with_heartbeat_timeout(self):
        """Test that workflow is configured with heartbeat timeout."""
        # This is more of an integration test to ensure the workflow configuration is correct
        @activity.defn(name="get_all_namespace_metrics")
        async def mock_get_all_namespace_metrics():
            # Simulate some processing time
            import asyncio
            from temporalio import activity
            
            for i in range(10):
                activity.heartbeat(f"Processing {i}")
                await asyncio.sleep(0.1)
            
            return [
                NamespaceRecommendation(
                    namespace="test.ns",
                    action_limit=500.0,
                    action_count=100.0,
                    recommended_trus=0,
                    current_capacity_mode="on-demand",
                    current_trus=None,
                    recommended_capacity_mode="on-demand",
                ),
            ]
        
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-heartbeat",
                workflows=[BulkCapacityAnalysisWorkflow],
                activities=[mock_get_all_namespace_metrics],
            ):
                result = await env.client.execute_workflow(
                    BulkCapacityAnalysisWorkflow.run,
                    id="test-heartbeat-workflow",
                    task_queue="test-heartbeat",
                )
                
                assert len(result) == 1
                assert result[0].namespace == "test.ns"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
