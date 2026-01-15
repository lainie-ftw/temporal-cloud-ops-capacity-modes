"""Activities for namespace operations."""

import logging
import math

from temporalio import activity

from ..cloud_ops_client import CloudOpsClient
from ..openmetrics_client import OpenMetricsClient
from ..config import get_settings
from ..models.types import NamespaceInfo, NamespaceMetrics, NamespaceRecommendation, ProvisioningState

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
    metrics for all namespaces, then fetches current capacity mode per namespace
    from Cloud Ops API, and calculates recommended TRUs and capacity mode.

    Returns:
        List of NamespaceRecommendation objects with metrics and recommendations

    Raises:
        Exception: If the API request fails
    """
    settings = get_settings()
    
    activity.logger.info("Activity: get_all_namespace_metrics started")
    
    metrics_client = OpenMetricsClient(
        api_key=settings.temporal_cloud_metrics_api_key,
        base_url=settings.cloud_metrics_api_base_url,
    )
    
    cloud_ops_client = CloudOpsClient(
        api_key=settings.temporal_cloud_ops_api_key,
        base_url=settings.cloud_ops_api_base_url,
    )
    
    try:
        # Make single API call to get all namespace metrics
        metrics_by_namespace = await metrics_client.get_all_namespace_metrics()
        
        activity.logger.info(
            f"Retrieved metrics for {len(metrics_by_namespace)} namespaces"
        )
        
        # Convert to NamespaceRecommendation objects
        recommendations = []
        processed_count = 0

        for namespace, metrics in metrics_by_namespace.items():
            # Filter based on allow/deny lists
            if not settings.should_manage_namespace(namespace):
                activity.logger.debug(f"Skipping filtered namespace: {namespace}")
                continue
            
            action_limit = metrics.get('action_limit', 0.0)
            action_count = metrics.get('action_count', 0.0)
            
            # Calculate recommended TRUs
            recommended_trus = _calculate_recommended_trus(action_limit, action_count)
            
            # Determine recommended capacity mode based on recommended TRUs
            if recommended_trus == 0:
                recommended_capacity_mode = "on-demand"
            else:
                recommended_capacity_mode = "provisioned"
            
            # Get current capacity mode from Cloud Ops API
            try:
                namespace_info = await cloud_ops_client.get_namespace_info(namespace)
                if namespace_info:
                    if namespace_info.provisioning_state == ProvisioningState.ENABLED:
                        current_capacity_mode = "provisioned"
                        current_trus = namespace_info.current_tru_count
                    else:
                        current_capacity_mode = "on-demand"
                        current_trus = None
                else:
                    # Namespace not found - use defaults
                    current_capacity_mode = "on-demand"
                    current_trus = None
                    activity.logger.warning(f"Namespace {namespace} not found in Cloud Ops API")
            except Exception as e:
                # Log error but continue with defaults
                activity.logger.error(f"Failed to get capacity mode for {namespace}: {e}")
                current_capacity_mode = "on-demand"
                current_trus = None
            
            recommendation = NamespaceRecommendation(
                namespace=namespace,
                action_limit=action_limit,
                action_count=action_count,
                recommended_trus=recommended_trus,
                current_capacity_mode=current_capacity_mode,
                current_trus=current_trus,
                recommended_capacity_mode=recommended_capacity_mode,
            )
            recommendations.append(recommendation)
            
            processed_count += 1
            
            # Send heartbeat every 5 namespaces
            if processed_count % 5 == 0:
                activity.heartbeat(f"Processed {processed_count}/{len(metrics_by_namespace)} namespaces")
                activity.logger.info(f"Heartbeat: Processed {processed_count}/{len(metrics_by_namespace)} namespaces")
            
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
        await metrics_client.close()
        await cloud_ops_client.close()


def calculate_minimum_charged_aps(trus: int) -> int:
    """
    Calculate the minimum APS charged for a given number of TRUs.
    
    Args:
        trus: Number of TRUs provisioned
        
    Returns:
        Minimum APS that will be charged
    """
    if trus == 0:
        return 0
    if trus == 1:
        return 0  # First TRU has no minimum
    return (trus - 1) * 100  # Each additional TRU has 100 APS minimum

def _calculate_recommended_trus(action_limit: float, action_count: float) -> int:
    """Calculate recommended number of TRUs based on metrics.

    Note: 1 TRU is equivalent to 0 TRUs (both provide 500 APS base capacity).
    This function will never recommend 1 TRU - it jumps from 0 to 2+ TRUs.
    
    Args:
        action_limit: The action limit for the namespace
        action_count: The current action count for the namespace
        
    Returns:
        Recommended number of TRUs (0 or 2+, never 1)
    """
    max_aps_per_tru = 500
    min_aps_per_additional_tru = 100
    
    # Calculate current TRUs from action_limit
    current_trus = math.floor(action_limit / max_aps_per_tru)
    
    # Treat 1 TRU as equivalent to 0 TRUs (same capacity)
    if current_trus <= 1:
        current_trus = 0
    
    # If no provisioning currently enabled (0 or 1 TRU)
    if current_trus == 0:
        # Only enable if we need more than base capacity (500 APS)
        if action_count > max_aps_per_tru:
            # Need provisioned capacity - round up to nearest TRU (minimum 2)
            return max(2, math.ceil(action_count / max_aps_per_tru))
        else:
            # Base capacity is sufficient
            return 0
    
    # Current capacity metrics
    max_capacity = current_trus * max_aps_per_tru
    utilization_percent = (action_count / max_capacity) * 100
    min_charged = calculate_minimum_charged_aps(current_trus)
    
    # Scale up: if using >= 80% of capacity, add 1 TRU
    if utilization_percent >= 80:
        return current_trus + 1
    
    # Scale down: if current usage is below minimum charged threshold
    if action_count < min_charged:
        # Check if usage is below base capacity - if so, recommend on-demand
        if action_count <= max_aps_per_tru:
            return 0
        
        # Calculate optimal TRUs for usage above base capacity
        # We want: action_count >= (optimal_trus - 1) * 100
        # So: optimal_trus <= (action_count / 100) + 1
        optimal_trus = math.floor(action_count / min_aps_per_additional_tru) + 1
        
        # Directly recommend the optimal TRU count (not gradual)
        # Never recommend 1 TRU (same as 0 TRUs)
        return max(2, optimal_trus)
    
    # No change needed - in the efficient zone
    return current_trus
