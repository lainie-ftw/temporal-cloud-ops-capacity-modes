"""Client for Temporal Cloud Ops API."""

import logging
from typing import Optional

import httpx

from .models.types import NamespaceInfo, NamespaceMetrics, ProvisioningState

logger = logging.getLogger(__name__)


class CloudOpsClient:
    """Client for interacting with Temporal Cloud Ops API."""

    def __init__(self, api_key: str, base_url: str = "https://saas-api.tmprl.cloud"):
        """Initialize the Cloud Ops API client.

        Args:
            api_key: API key for authentication
            base_url: Base URL for the Cloud Ops API
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def list_namespaces(self) -> list[NamespaceInfo]:
        """List all namespaces in the account with their provisioning state.

        Returns:
            List of NamespaceInfo objects

        Raises:
            httpx.HTTPError: If the API request fails
        """
        logger.info("Fetching list of namespaces from Cloud Ops API")

        try:
            response = await self.client.get(f"{self.base_url}/cloud/namespaces")
            response.raise_for_status()
            data = response.json()

            namespaces = []
            for ns_data in data.get("namespaces", []):
                namespace_name = ns_data.get("namespace")
                spec = ns_data.get("spec", {})

                # Check capacity using the new API structure
                capacity = ns_data.get("capacity", {})
                provisioned = capacity.get("provisioned", {})
                tru_count = provisioned.get("currentValue")
                
                if tru_count and tru_count > 0:
                    provisioning_state = ProvisioningState.ENABLED
                else:
                    provisioning_state = ProvisioningState.DISABLED
                    tru_count = None

                # Get regions (array in new API)
                regions = spec.get("regions", [])
                region = regions[0] if regions else None

                namespaces.append(
                    NamespaceInfo(
                        namespace=namespace_name,
                        provisioning_state=provisioning_state,
                        current_tru_count=tru_count,
                        region=region,
                    )
                )

            logger.info(f"Found {len(namespaces)} namespaces")
            return namespaces

        except httpx.HTTPError as e:
            logger.error(f"Failed to list namespaces: {e}")
            raise

    async def get_namespace_metrics(self, namespace: str) -> NamespaceMetrics:
        """Get metrics for a namespace to determine if action is needed.

        Args:
            namespace: The namespace to check

        Returns:
            NamespaceMetrics object with usage and throttling information

        Raises:
            httpx.HTTPError: If the API request fails
        """
        logger.info(f"Fetching metrics for namespace: {namespace}")

        try:
            # Get namespace usage metrics
            response = await self.client.get(
                f"{self.base_url}/api/v1/namespaces/{namespace}/usage"
            )
            response.raise_for_status()
            data = response.json()

            # Extract metrics
            # Note: The actual structure depends on the Cloud Ops API response
            usage = data.get("usage", {})
            actions_per_hour = usage.get("actionsPerHour", 0)

            # Check throttling
            throttle_data = usage.get("throttle", {})
            is_throttled = throttle_data.get("isThrottled", False)
            throttle_percentage = throttle_data.get("percentage", 0.0)

            metrics = NamespaceMetrics(
                namespace=namespace,
                actions_per_hour=actions_per_hour,
                is_throttled=is_throttled,
                throttle_percentage=throttle_percentage,
            )

            logger.info(f"Metrics for {namespace}: {metrics}")
            return metrics

        except httpx.HTTPError as e:
            logger.error(f"Failed to get metrics for {namespace}: {e}")
            raise

    async def enable_provisioning(self, namespace: str, tru_count: int) -> bool:
        """Enable provisioned capacity for a namespace.

        Args:
            namespace: The namespace to enable provisioning for
            tru_count: Number of TRUs to provision

        Returns:
            True if successful

        Raises:
            httpx.HTTPError: If the API request fails
        """
        logger.info(f"Enabling provisioning for {namespace} with {tru_count} TRUs")

        try:
            # First, get the namespace to get the resourceVersion
            ns_response = await self.client.get(
                f"{self.base_url}/cloud/namespaces/{namespace}"
            )
            ns_response.raise_for_status()
            ns_data = ns_response.json()
            resource_version = ns_data.get("namespace", {}).get("resourceVersion")

            # Use the new capacitySpec format
            payload = {
                "spec": {
                    "capacitySpec": {
                        "provisioned": {
                            "value": tru_count
                        }
                    }
                },
                "resourceVersion": resource_version
            }

            response = await self.client.post(
                f"{self.base_url}/cloud/namespaces/{namespace}",
                json=payload,
            )
            response.raise_for_status()

            logger.info(f"Successfully enabled provisioning for {namespace}")
            return True

        except httpx.HTTPError as e:
            logger.error(f"Failed to enable provisioning for {namespace}: {e}")
            raise

    async def disable_provisioning(self, namespace: str) -> bool:
        """Disable provisioned capacity for a namespace.

        Args:
            namespace: The namespace to disable provisioning for

        Returns:
            True if successful

        Raises:
            httpx.HTTPError: If the API request fails
        """
        logger.info(f"Disabling provisioning for {namespace}")

        try:
            # First, get the namespace to get the resourceVersion
            ns_response = await self.client.get(
                f"{self.base_url}/cloud/namespaces/{namespace}"
            )
            ns_response.raise_for_status()
            ns_data = ns_response.json()
            resource_version = ns_data.get("namespace", {}).get("resourceVersion")

            # Use onDemand capacity mode to disable provisioning
            payload = {
                "spec": {
                    "capacitySpec": {
                        "onDemand": {}
                    }
                },
                "resourceVersion": resource_version
            }

            response = await self.client.post(
                f"{self.base_url}/cloud/namespaces/{namespace}",
                json=payload,
            )
            response.raise_for_status()

            logger.info(f"Successfully disabled provisioning for {namespace}")
            return True

        except httpx.HTTPError as e:
            logger.error(f"Failed to disable provisioning for {namespace}: {e}")
            raise

    async def get_namespace_info(self, namespace: str) -> Optional[NamespaceInfo]:
        """Get information about a specific namespace.

        Args:
            namespace: The namespace to get information for

        Returns:
            NamespaceInfo object or None if not found

        Raises:
            httpx.HTTPError: If the API request fails
        """
        logger.info(f"Fetching info for namespace: {namespace}")

        try:
            response = await self.client.get(
                f"{self.base_url}/cloud/namespaces/{namespace}"
            )
            response.raise_for_status()
            data = response.json()
            ns_data = data.get("namespace", {})

            spec = ns_data.get("spec", {})
            
            # Check capacity using the new API structure
            capacity = ns_data.get("capacity", {})
            provisioned = capacity.get("provisioned", {})
            tru_count = provisioned.get("currentValue")
            
            if tru_count and tru_count > 0:
                provisioning_state = ProvisioningState.ENABLED
            else:
                provisioning_state = ProvisioningState.DISABLED
                tru_count = None

            # Get regions (array in new API)
            regions = spec.get("regions", [])
            region = regions[0] if regions else None

            return NamespaceInfo(
                namespace=ns_data.get("namespace"),
                provisioning_state=provisioning_state,
                current_tru_count=tru_count,
                region=region,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Namespace not found: {namespace}")
                return None
            raise
        except httpx.HTTPError as e:
            logger.error(f"Failed to get namespace info for {namespace}: {e}")
            raise
