"""Tests for OpenMetrics client."""

import pytest
from src.openmetrics_client import OpenMetricsClient


def test_parse_openmetrics():
    """Test parsing of OpenMetrics format."""
    client = OpenMetricsClient(api_key="test-key")
    
    # Sample OpenMetrics response
    openmetrics_text = """# TYPE temporal_cloud_v1_workflow_success_count gauge
# HELP temporal_cloud_v1_workflow_success_count The number of successful workflows per second
temporal_cloud_v1_workflow_success_count{temporal_namespace="production",temporal_workflow_type="payment-processing",region="aws-us-west-2"} 0.0116 1609459200000
temporal_cloud_v1_workflow_success_count{temporal_namespace="production",temporal_workflow_type="order-fulfillment",region="aws-us-west-2"} 0.0355 1609459200000
temporal_cloud_v1_workflow_success_count{temporal_namespace="staging",temporal_workflow_type="test-workflow",region="aws-us-west-2"} 0.001 1609459200000
# TYPE temporal_cloud_v1_workflow_failed_count gauge
# HELP temporal_cloud_v1_workflow_failed_count The number of failed workflows per second
temporal_cloud_v1_workflow_failed_count{temporal_namespace="production",temporal_workflow_type="payment-processing",region="aws-us-west-2"} 0.0001 1609459200000
# TYPE temporal_cloud_v1_resource_exhausted_count gauge
# HELP temporal_cloud_v1_resource_exhausted_count Resource exhausted errors per second
temporal_cloud_v1_resource_exhausted_count{temporal_namespace="production",region="aws-us-west-2"} 0.005 1609459200000
"""
    
    metrics = client._parse_openmetrics(openmetrics_text, "production")
    
    # Check that metrics were parsed correctly
    assert "temporal_cloud_v1_workflow_success_count" in metrics
    assert metrics["temporal_cloud_v1_workflow_success_count"] == pytest.approx(0.0471, rel=0.001)  # 0.0116 + 0.0355
    
    assert "temporal_cloud_v1_workflow_failed_count" in metrics
    assert metrics["temporal_cloud_v1_workflow_failed_count"] == pytest.approx(0.0001, rel=0.001)
    
    assert "temporal_cloud_v1_resource_exhausted_count" in metrics
    assert metrics["temporal_cloud_v1_resource_exhausted_count"] == pytest.approx(0.005, rel=0.001)
    
    # Staging namespace should not be included
    staging_metrics = client._parse_openmetrics(openmetrics_text, "staging")
    assert staging_metrics["temporal_cloud_v1_workflow_success_count"] == pytest.approx(0.001, rel=0.001)


def test_calculate_actions_per_hour():
    """Test calculation of actions per hour."""
    client = OpenMetricsClient(api_key="test-key")
    
    # 0.0472 workflows per second = ~170 per hour
    metrics = {
        "temporal_cloud_v1_workflow_success_count": 0.04,
        "temporal_cloud_v1_workflow_failed_count": 0.0072,
    }
    
    actions_per_hour = client._calculate_actions_per_hour(metrics)
    assert actions_per_hour == int((0.04 + 0.0072) * 3600)  # 170
    

def test_check_throttling():
    """Test throttling detection."""
    client = OpenMetricsClient(api_key="test-key")
    
    # Test with throttling
    metrics_throttled = {
        "temporal_cloud_v1_workflow_success_count": 0.1,
        "temporal_cloud_v1_workflow_failed_count": 0.01,
        "temporal_cloud_v1_resource_exhausted_count": 0.005,
    }
    
    is_throttled, percentage = client._check_throttling(metrics_throttled)
    assert is_throttled is True
    assert percentage == pytest.approx(4.545, rel=0.01)  # 0.005 / (0.1 + 0.01) * 100
    
    # Test without throttling
    metrics_no_throttle = {
        "temporal_cloud_v1_workflow_success_count": 0.1,
        "temporal_cloud_v1_workflow_failed_count": 0.01,
    }
    
    is_throttled, percentage = client._check_throttling(metrics_no_throttle)
    assert is_throttled is False
    assert percentage == 0.0


def test_parse_openmetrics_no_namespace_match():
    """Test that only metrics for the specified namespace are returned."""
    client = OpenMetricsClient(api_key="test-key")
    
    openmetrics_text = """temporal_cloud_v1_workflow_success_count{temporal_namespace="other-namespace"} 1.0 1609459200000
temporal_cloud_v1_workflow_success_count{temporal_namespace="production"} 2.0 1609459200000
"""
    
    metrics = client._parse_openmetrics(openmetrics_text, "production")
    assert metrics["temporal_cloud_v1_workflow_success_count"] == 2.0
    
    metrics_other = client._parse_openmetrics(openmetrics_text, "other-namespace")
    assert metrics_other["temporal_cloud_v1_workflow_success_count"] == 1.0
