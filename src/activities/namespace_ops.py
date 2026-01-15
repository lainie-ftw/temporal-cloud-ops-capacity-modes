"""Activities for namespace operations."""

import logging

from temporalio import activity

from ..cloud_ops_client import CloudOpsClient
from ..openmetrics_client import OpenMetricsClient
from ..config import get_settings
from ..models.types import NamespaceInfo, NamespaceMetrics, NamespaceRecommendation

logger = logging.getLogger(__name__)


@activity.defn
async def list_namespaces() -> list[NamespaceInfo]:
    """List all namespaces with their current provisioning state.

    Returns:
        List of NamespaceInfo objects

    Raises:
        Exception: If the API request fails
    """
    settings = get_settings()
    
    activity.logger.info("Activity: list_namespaces started")
    
    client = CloudOpsClient(
        api_key=settings.temporal_cloud_ops_api_key,
        base_url=settings.cloud_ops_api_base_url,
    )
    
    try:
        namespaces = await client.list_namespaces()
        
        # Filter based on allow/deny lists
        filtered_namespaces = [
            ns for ns in namespaces
            if settings.should_manage_namespace(ns.namespace)
        ]
        
        activity.logger.info(
            f"Listed {len(namespaces)} namespaces, "
            f"{len(filtered_namespaces)} after filtering"
        )
        
        return filtered_namespaces
        
    except Exception as e:
        activity.logger.error(f"Failed to list namespaces: {e}")
        raise
    finally:
        await client.close()


@activity.defn
async def check_throttling(namespace: str) -> NamespaceMetrics:
    """Check if a namespace is being throttled and get its metrics.

    This activity uses the Temporal Cloud OpenMetrics API to retrieve
    real-time metrics about workflow execution rates and throttling status.

    Args:
        namespace: The namespace to check

    Returns:
        NamespaceMetrics object with usage and throttling information

    Raises:
        Exception: If the API request fails
    """
    settings = get_settings()
    
    activity.logger.info(f"Activity: check_throttling for {namespace}")
    
    client = OpenMetricsClient(
        api_key=settings.temporal_cloud_metrics_api_key,
        base_url=settings.cloud_metrics_api_base_url,
    )
    
    try:
        metrics = await client.get_namespace_metrics(namespace)
        
        activity.logger.info(
            f"Namespace {namespace} metrics: "
            f"{metrics.actions_per_hour} actions/hour, "
            f"throttled: {metrics.is_throttled}"
        )
        
        return metrics
        
    except Exception as e:
        activity.logger.error(f"Failed to check throttling for {namespace}: {e}")
        raise
    finally:
        await client.close()


@activity.defn
async def get_all_namespace_metrics() -> list[NamespaceRecommendation]:
    """Get metrics for all namespaces in a single API call.

    This activity makes ONE API call to fetch action limit and action count
    metrics for all namespaces, then calculates recommended TRUs for each.

    Returns:
        List of NamespaceRecommendation objects with metrics and recommendations

    Raises:
        Exception: If the API request fails
    """
    settings = get_settings()
    
    activity.logger.info("Activity: get_all_namespace_metrics started")
    
    client = OpenMetricsClient(
        api_key=settings.temporal_cloud_metrics_api_key,
        base_url=settings.cloud_metrics_api_base_url,
    )
    
    try:
        # Make single API call to get all namespace metrics
        metrics_by_namespace = await client.get_all_namespace_metrics()
        
        activity.logger.info(
            f"Retrieved metrics for {len(metrics_by_namespace)} namespaces"
        )
        
        # Convert to NamespaceRecommendation objects
        recommendations = []
        for namespace, metrics in metrics_by_namespace.items():
            # Filter based on allow/deny lists
            if not settings.should_manage_namespace(namespace):
                activity.logger.debug(f"Skipping filtered namespace: {namespace}")
                continue
            
            action_limit = metrics.get('action_limit', 0.0)
            action_count = metrics.get('action_count', 0.0)
            
            # Calculate recommended TRUs (stubbed for now)
            # TODO: Implement actual TRU recommendation logic
            recommended_trus = _calculate_recommended_trus(action_limit, action_count)
            
            recommendation = NamespaceRecommendation(
                namespace=namespace,
                action_limit=action_limit,
                action_count=action_count,
                recommended_trus=recommended_trus,
            )
            recommendations.append(recommendation)
            
            activity.logger.debug(str(recommendation))
        
        activity.logger.info(
            f"Generated {len(recommendations)} recommendations "
            f"after filtering"
        )
        
        return recommendations
        
    except Exception as e:
        activity.logger.error(f"Failed to get all namespace metrics: {e}")
        raise
    finally:
        await client.close()


def _calculate_recommended_trus(action_limit: float, action_count: float) -> int:
    """Calculate recommended number of TRUs based on metrics.

    This is a stubbed implementation that returns a placeholder value.
    
    Args:
        action_limit: The action limit for the namespace
        action_count: The current action count for the namespace
        
    Returns:
        Recommended number of TRUs (stubbed to return 5)
    """
    # TODO: Implement actual TRU recommendation logic
    # This could consider:
    # - Current usage vs limit ratio
    # - Historical trends
    # - Growth projections
    # - Cost optimization targets
    
    # For now, return a stubbed value
    return 5
