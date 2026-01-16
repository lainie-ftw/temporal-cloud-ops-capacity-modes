"""Activities for provisioning operations."""

import logging

from temporalio import activity

from ..cloud_ops_client import CloudOpsClient
from ..config import get_settings

logger = logging.getLogger(__name__)


@activity.defn
async def enable_provisioning(namespace: str, tru_count: int) -> bool:
    """Enable provisioned capacity for a namespace.

    This activity is idempotent - it checks current state before making changes.

    Args:
        namespace: The namespace to enable provisioning for
        tru_count: Number of TRUs to provision

    Returns:
        True if successful

    Raises:
        Exception: If the API request fails
    """
    settings = get_settings()
    
    activity.logger.info(
        f"Activity: enable_provisioning for {namespace} with {tru_count} TRUs"
    )
    
    # In dry run mode, just log and return
    if settings.dry_run_mode:
        activity.logger.info(
            f"[DRY RUN] Would enable provisioning for {namespace} with {tru_count} TRUs"
        )
        return True
    
    client = CloudOpsClient(
        api_key=settings.temporal_cloud_ops_api_key,
        base_url=settings.cloud_ops_api_base_url,
    )
    
    try:
        # Get the namespace to retrieve current spec and resource version
        ns_response = await client.client.get(
            f"{client.base_url}/cloud/namespaces/{namespace}"
        )
        ns_response.raise_for_status()
        ns_data = ns_response.json()
        namespace_obj = ns_data.get("namespace", {})
        current_spec = namespace_obj.get("spec", {})
        resource_version = namespace_obj.get("resourceVersion")

        # Check current state for idempotency
        capacity = namespace_obj.get("capacity", {})
        provisioned = capacity.get("provisioned", {})
        current_tru_count = provisioned.get("currentValue")
        
        if current_tru_count == tru_count:
            activity.logger.info(
                f"Namespace {namespace} already has {tru_count} TRUs enabled, skipping"
            )
            return True
        
        # Enable provisioning with current spec and resource version
        result = await client.enable_provisioning(
            namespace, tru_count, current_spec, resource_version
        )
        
        activity.logger.info(
            f"Successfully enabled provisioning for {namespace} with {tru_count} TRUs"
        )
        
        return result
        
    except Exception as e:
        activity.logger.error(f"Failed to enable provisioning for {namespace}: {e}")
        raise
    finally:
        await client.close()


@activity.defn
async def disable_provisioning(namespace: str) -> bool:
    """Disable provisioned capacity for a namespace.

    This activity is idempotent - it checks current state before making changes.

    Args:
        namespace: The namespace to disable provisioning for

    Returns:
        True if successful

    Raises:
        Exception: If the API request fails
    """
    settings = get_settings()
    
    activity.logger.info(f"Activity: disable_provisioning for {namespace}")
    
    # In dry run mode, just log and return
    if settings.dry_run_mode:
        activity.logger.info(f"[DRY RUN] Would disable provisioning for {namespace}")
        return True
    
    client = CloudOpsClient(
        api_key=settings.temporal_cloud_ops_api_key,
        base_url=settings.cloud_ops_api_base_url,
    )
    
    try:
        # Get the namespace to retrieve current spec and resource version
        ns_response = await client.client.get(
            f"{client.base_url}/cloud/namespaces/{namespace}"
        )
        ns_response.raise_for_status()
        ns_data = ns_response.json()
        namespace_obj = ns_data.get("namespace", {})
        current_spec = namespace_obj.get("spec", {})
        resource_version = namespace_obj.get("resourceVersion")

        # Check current state for idempotency
        capacity = namespace_obj.get("capacity", {})
        provisioned = capacity.get("provisioned", {})
        current_tru_count = provisioned.get("currentValue")
        
        if current_tru_count is None:
            activity.logger.info(
                f"Namespace {namespace} already has provisioning disabled, skipping"
            )
            return True
        
        # Disable provisioning with current spec and resource version
        result = await client.disable_provisioning(
            namespace, current_spec, resource_version
        )
        
        activity.logger.info(f"Successfully disabled provisioning for {namespace}")
        
        return result
        
    except Exception as e:
        activity.logger.error(f"Failed to disable provisioning for {namespace}: {e}")
        raise
    finally:
        await client.close()
