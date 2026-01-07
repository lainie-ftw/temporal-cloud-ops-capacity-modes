"""Activities for namespace operations."""

import logging

from temporalio import activity

from ..cloud_ops_client import CloudOpsClient
from ..config import get_settings
from ..models.types import NamespaceInfo, NamespaceMetrics

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

    Args:
        namespace: The namespace to check

    Returns:
        NamespaceMetrics object with usage and throttling information

    Raises:
        Exception: If the API request fails
    """
    settings = get_settings()
    
    activity.logger.info(f"Activity: check_throttling for {namespace}")
    
    client = CloudOpsClient(
        api_key=settings.temporal_cloud_ops_api_key,
        base_url=settings.cloud_ops_api_base_url,
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
