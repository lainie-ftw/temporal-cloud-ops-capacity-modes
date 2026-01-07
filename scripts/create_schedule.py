"""Script to create the Temporal Schedule for capacity management."""

import asyncio
import logging
import sys
from pathlib import Path

from temporalio.client import Client, TLSConfig, Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleCalendarSpec, ScheduleOverlapPolicy

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.workflows.capacity_management import CapacityManagementWorkflow, CapacityManagementInput

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Create or update the Temporal Schedule for capacity management."""
    # Load settings
    try:
        settings = get_settings()
        settings.validate_auth_config()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Please ensure all required environment variables are set")
        sys.exit(1)

    logger.info(f"Creating schedule for namespace: {settings.temporal_namespace}")

    # Configure authentication
    try:
        if settings.use_api_key_auth():
            logger.info("Using API key authentication")
            client = await Client.connect(
                settings.temporal_address,
                namespace=settings.temporal_namespace,
                api_key=settings.temporal_api_key,
            )
        else:
            logger.info("Using mTLS certificate authentication")
            with open(settings.temporal_cert_path, "rb") as f:
                client_cert = f.read()
            with open(settings.temporal_key_path, "rb") as f:
                client_key = f.read()

            tls_config = TLSConfig(
                client_cert=client_cert,
                client_private_key=client_key,
            )
            
            client = await Client.connect(
                settings.temporal_address,
                namespace=settings.temporal_namespace,
                tls=tls_config,
            )
        
        logger.info(f"Connected to Temporal at {settings.temporal_address}")
    except Exception as e:
        logger.error(f"Failed to connect to Temporal: {e}")
        sys.exit(1)

    # Define the schedule
    schedule_id = "capacity-management-schedule"
    
    # Create workflow input
    workflow_input = CapacityManagementInput(
        default_tru_count=settings.default_tru_count,
        min_actions_threshold=settings.min_actions_threshold,
        dry_run=settings.dry_run_mode,
    )

    # Create the schedule
    try:
        schedule = await client.create_schedule(
            schedule_id,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    CapacityManagementWorkflow.run,
                    workflow_input,
                    id=f"capacity-management-workflow",
                    task_queue=settings.task_queue,
                ),
                spec=ScheduleSpec(
                    # Trigger at 45 minutes past every hour
                    calendars=[
                        ScheduleCalendarSpec(
                            minute="45",
                            hour="*",
                        )
                    ],
                ),
                # Skip if previous run is still running
                policy=ScheduleOverlapPolicy.SKIP,
            ),
        )
        
        logger.info(f"✓ Successfully created schedule: {schedule_id}")
        logger.info(f"  - Trigger: 45 minutes past every hour")
        logger.info(f"  - Overlap policy: SKIP")
        logger.info(f"  - Task queue: {settings.task_queue}")
        logger.info(f"  - Dry run mode: {settings.dry_run_mode}")
        logger.info(f"  - Default TRUs: {settings.default_tru_count}")
        logger.info(f"  - Min actions threshold: {settings.min_actions_threshold}")
        
    except Exception as e:
        if "already exists" in str(e).lower():
            logger.warning(f"Schedule {schedule_id} already exists")
            logger.info("To update the schedule, delete it first with:")
            logger.info(f"  temporal schedule delete --schedule-id {schedule_id}")
        else:
            logger.error(f"Failed to create schedule: {e}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
