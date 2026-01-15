"""Client for Temporal Cloud OpenMetrics API."""

import logging
import re
from typing import Optional

import httpx

from .models.types import NamespaceMetrics

logger = logging.getLogger(__name__)


class OpenMetricsClient:
    """Client for interacting with Temporal Cloud OpenMetrics API."""

    def __init__(self, api_key: str, base_url: str = "https://metrics.temporal.io"):
        """Initialize the OpenMetrics API client.

        Args:
            api_key: API key for authentication (Metrics Read-Only role)
            base_url: Base URL for the OpenMetrics API
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=30.0,
        )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def get_all_namespace_metrics(self) -> dict[str, dict[str, float]]:
        """Get action limit and action count metrics for all namespaces.

        This method queries the OpenMetrics API using the metrics query parameter
        to filter for only the specific metrics we need, reducing response size.

        Returns:
            Dictionary mapping namespace to metrics dict containing:
            - 'action_limit': temporal_cloud_v1_action_limit
            - 'action_count': temporal_cloud_v1_total_action_count

        Raises:
            httpx.HTTPError: If the API request fails
        """
        logger.info("Fetching OpenMetrics for all namespaces")

        try:
            # Query metrics with filtering to get only specific metrics
            # Using query parameters to reduce response size at the API level
            response = await self.client.get(
                f"{self.base_url}/v1/metrics",
                params={
                    "metrics": [
                        "temporal_cloud_v1_action_limit",
                        "temporal_cloud_v1_total_action_count",
                    ]
                },
            )
            response.raise_for_status()

            # Check response completeness
            completeness = response.headers.get("X-Completeness", "unknown")
            if completeness != "complete":
                logger.warning(
                    f"Metrics response is {completeness}, data may be incomplete"
                )

            # Parse OpenMetrics format for all namespaces
            metrics_by_namespace = self._parse_all_namespace_metrics(response.text)

            logger.info(f"Retrieved metrics for {len(metrics_by_namespace)} namespaces")
            return metrics_by_namespace

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error(
                    f"Rate limited when fetching metrics. "
                    f"Retry-After: {e.response.headers.get('Retry-After')} seconds"
                )
            raise
        except httpx.HTTPError as e:
            logger.error(f"Failed to get metrics for all namespaces: {e}")
            raise

    async def get_namespace_metrics(self, namespace: str) -> NamespaceMetrics:
        """Get metrics for a namespace to determine if action is needed.

        This method queries the OpenMetrics API and parses the response to calculate:
        - Actions per hour based on workflow success/failure rates
        - Throttling status based on resource exhausted errors

        Args:
            namespace: The namespace to check

        Returns:
            NamespaceMetrics object with usage and throttling information

        Raises:
            httpx.HTTPError: If the API request fails
        """
        logger.info(f"Fetching OpenMetrics for namespace: {namespace}")

        try:
            # Query metrics for the specific namespace
            response = await self.client.get(
                f"{self.base_url}/v1/metrics",
                params={"namespaces": namespace},
            )
            response.raise_for_status()

            # Check response completeness
            completeness = response.headers.get("X-Completeness", "unknown")
            if completeness != "complete":
                logger.warning(
                    f"Metrics response for {namespace} is {completeness}, "
                    "data may be incomplete"
                )

            # Parse OpenMetrics format
            metrics_data = self._parse_openmetrics(response.text, namespace)

            # Calculate actions per hour from workflow completion rates
            actions_per_hour = self._calculate_actions_per_hour(metrics_data)

            # Check for throttling indicators
            is_throttled, throttle_percentage = self._check_throttling(metrics_data)

            result = NamespaceMetrics(
                namespace=namespace,
                actions_per_hour=actions_per_hour,
                is_throttled=is_throttled,
                throttle_percentage=throttle_percentage,
            )

            logger.info(f"Metrics for {namespace}: {result}")
            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error(
                    f"Rate limited when fetching metrics for {namespace}. "
                    f"Retry-After: {e.response.headers.get('Retry-After')} seconds"
                )
            raise
        except httpx.HTTPError as e:
            logger.error(f"Failed to get metrics for {namespace}: {e}")
            raise

    def _parse_all_namespace_metrics(self, text: str) -> dict[str, dict[str, float]]:
        """Parse OpenMetrics format text for all namespaces.

        Args:
            text: OpenMetrics format text response

        Returns:
            Dictionary mapping namespace to dict of metrics
            Each namespace dict contains:
            - 'action_limit': temporal_cloud_v1_action_limit
            - 'action_count': temporal_cloud_v1_total_action_count
        """
        namespace_metrics = {}
        
        # OpenMetrics format: metric_name{label="value",...} value timestamp
        pattern = re.compile(
            r'^([a-zA-Z_][a-zA-Z0-9_]*)\{([^}]*)\}\s+([\d.]+)(?:\s+\d+)?$'
        )
        
        # Metrics we're interested in
        target_metrics = {
            'temporal_cloud_v1_action_limit',
            'temporal_cloud_v1_total_action_count'
        }
        
        for line in text.split('\n'):
            line = line.strip()
            
            # Skip comments and TYPE/HELP lines
            if line.startswith('#') or not line:
                continue
            
            match = pattern.match(line)
            if match:
                metric_name = match.group(1)
                
                # Skip metrics we're not interested in
                if metric_name not in target_metrics:
                    continue
                
                labels_str = match.group(2)
                value = float(match.group(3))
                
                # Parse labels
                labels = {}
                label_pattern = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"')
                for label_match in label_pattern.finditer(labels_str):
                    labels[label_match.group(1)] = label_match.group(2)
                
                # Get the namespace from labels
                namespace = labels.get('temporal_namespace')
                if not namespace:
                    continue
                
                # Initialize namespace dict if needed
                if namespace not in namespace_metrics:
                    namespace_metrics[namespace] = {
                        'action_limit': 0.0,
                        'action_count': 0.0
                    }
                
                # Store the metric value
                if metric_name == 'temporal_cloud_v1_action_limit':
                    namespace_metrics[namespace]['action_limit'] = value
                elif metric_name == 'temporal_cloud_v1_total_action_count':
                    namespace_metrics[namespace]['action_count'] = value
        
        return namespace_metrics

    def _parse_openmetrics(self, text: str, namespace: str) -> dict[str, float]:
        """Parse OpenMetrics format text into a dictionary of metric values.

        Args:
            text: OpenMetrics format text response
            namespace: The namespace to filter for

        Returns:
            Dictionary mapping metric names to their values
        """
        metrics = {}
        
        # OpenMetrics format: metric_name{label="value",...} value timestamp
        # Example: temporal_cloud_v1_workflow_success_count{temporal_namespace="prod"} 42.0 1609459200000
        pattern = re.compile(
            r'^([a-zA-Z_][a-zA-Z0-9_]*)\{([^}]*)\}\s+([\d.]+)(?:\s+\d+)?$'
        )
        
        for line in text.split('\n'):
            line = line.strip()
            
            # Skip comments and TYPE/HELP lines
            if line.startswith('#') or not line:
                continue
            
            match = pattern.match(line)
            if match:
                metric_name = match.group(1)
                labels_str = match.group(2)
                value = float(match.group(3))
                
                # Parse labels
                labels = {}
                label_pattern = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"')
                for label_match in label_pattern.finditer(labels_str):
                    labels[label_match.group(1)] = label_match.group(2)
                
                # Only include metrics for our namespace
                if labels.get('temporal_namespace') == namespace:
                    # Create a key that includes relevant label info
                    key = metric_name
                    if 'temporal_workflow_type' in labels:
                        key = f"{metric_name}:{labels['temporal_workflow_type']}"
                    
                    # Aggregate metrics (sum across all workflow types, task queues, etc.)
                    metrics[metric_name] = metrics.get(metric_name, 0.0) + value
        
        return metrics

    def _calculate_actions_per_hour(self, metrics: dict[str, float]) -> int:
        """Calculate actions per hour from workflow completion metrics.

        The OpenMetrics API returns per-second rates, so we multiply by 3600
        to get per-hour rates.

        Args:
            metrics: Parsed metrics dictionary

        Returns:
            Estimated actions per hour
        """
        # Workflow completion metrics are per-second rates
        # Sum successful and failed workflows to get total actions per second
        success_per_sec = metrics.get('temporal_cloud_v1_workflow_success_count', 0.0)
        failed_per_sec = metrics.get('temporal_cloud_v1_workflow_failed_count', 0.0)
        
        # Also consider workflow starts as actions
        started_per_sec = metrics.get('temporal_cloud_v1_workflow_start_count', 0.0)
        
        # Use the max of completions or starts as the primary indicator
        actions_per_sec = max(success_per_sec + failed_per_sec, started_per_sec)
        
        # Convert to per hour
        actions_per_hour = int(actions_per_sec * 3600)
        
        logger.debug(
            f"Calculated actions/hour: {actions_per_hour} "
            f"(success: {success_per_sec}/s, failed: {failed_per_sec}/s, "
            f"started: {started_per_sec}/s)"
        )
        
        return actions_per_hour

    def _check_throttling(self, metrics: dict[str, float]) -> tuple[bool, float]:
        """Check if the namespace is being throttled.

        Throttling is indicated by resource_exhausted errors.

        Args:
            metrics: Parsed metrics dictionary

        Returns:
            Tuple of (is_throttled, throttle_percentage)
        """
        # Check for resource exhausted errors which indicate throttling
        resource_exhausted = metrics.get(
            'temporal_cloud_v1_resource_exhausted_count', 0.0
        )
        
        # Get total request rate to calculate percentage
        total_requests = (
            metrics.get('temporal_cloud_v1_workflow_success_count', 0.0)
            + metrics.get('temporal_cloud_v1_workflow_failed_count', 0.0)
            + metrics.get('temporal_cloud_v1_workflow_start_count', 0.0)
        )
        
        # If we're seeing resource exhausted errors, we're being throttled
        is_throttled = resource_exhausted > 0
        
        # Calculate throttle percentage
        throttle_percentage = 0.0
        if is_throttled and total_requests > 0:
            throttle_percentage = (resource_exhausted / total_requests) * 100
        
        logger.debug(
            f"Throttling check: is_throttled={is_throttled}, "
            f"percentage={throttle_percentage:.2f}%, "
            f"resource_exhausted={resource_exhausted}/s"
        )
        
        return is_throttled, throttle_percentage
