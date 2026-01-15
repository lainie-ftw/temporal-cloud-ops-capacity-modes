"""Script to create the Temporal Schedule for capacity management."""

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from temporalio.client import Client, Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleCalendarSpec, ScheduleOverlapPolicy
from temporalio.envconfig import ClientConfig

# Load environment variables from .env file
load_dotenv()

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
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Please ensure all required environment variables are set")
        sys.exit(1)

    logger.info("Creating capacity management schedule")

    # Connect to Temporal using environment configuration
    try:
        connect_config = ClientConfig.load_client_connect_config()
        logger.info(f"Connecting to Temporal at {connect_config.get('target_host')}")
        logger.info(f"Namespace: {connect_config.get('namespace')}")
        
        client = await Client.connect(**connect_config)
        logger.info("Successfully connected to Temporal")
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
