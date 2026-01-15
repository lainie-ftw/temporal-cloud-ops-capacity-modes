"""Bulk capacity analysis workflow."""

import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..models.types import NamespaceRecommendation
    from ..activities import get_all_namespace_metrics

logger = logging.getLogger(__name__)


@workflow.defn
class BulkCapacityAnalysisWorkflow:
    """Workflow that analyzes capacity for all namespaces in a single API call.

    This workflow:
    1. Makes ONE API call to get action limit and action count for all namespaces
    2. Calculates recommended TRUs for each namespace
    3. Returns a list of recommendations
    
    This is a simpler, read-only workflow compared to CapacityManagementWorkflow.
    It doesn't take any provisioning actions, just provides analysis.
    """

    @workflow.run
    async def run(self) -> list[NamespaceRecommendation]:
        """Execute the bulk capacity analysis workflow.

        Returns:
            List of NamespaceRecommendation objects with metrics and recommendations
        """
        workflow.logger.info("Starting bulk capacity analysis workflow")

        try:
            # Make single API call to get all namespace metrics and recommendations
            recommendations = await workflow.execute_activity(
                get_all_namespace_metrics,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=30),
                    maximum_attempts=3,
                    backoff_coefficient=2.0,
                ),
            )

            workflow.logger.info(
                f"Workflow completed: analyzed {len(recommendations)} namespaces"
            )
            
            # Log summary
            for rec in recommendations:
                workflow.logger.info(str(rec))

            return recommendations

        except Exception as e:
            error_msg = f"Fatal error in workflow: {str(e)}"
            workflow.logger.error(error_msg)
            raise

    @workflow.query
    def get_status(self) -> str:
        """Query to get current workflow status.

        Returns:
            Status string
        """
        return "Bulk capacity analysis workflow"
