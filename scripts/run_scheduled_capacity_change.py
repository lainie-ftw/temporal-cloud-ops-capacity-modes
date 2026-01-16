"""Script to manually execute a scheduled capacity change workflow (for testing)."""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.envconfig import ClientConfig

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.workflows.scheduled_capacity_change import (
    ScheduledCapacityChangeWorkflow,
)
from src.models.types import ScheduledCapacityChangeInput

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Manually execute a scheduled capacity change workflow once."""
    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Please ensure all required environment variables are set")
        sys.exit(1)

    # Parse command-line arguments
    if len(sys.argv) < 3:
        print("Usage: python run_scheduled_capacity_change.py <namespace> <tru_count> [end_time_minutes]")
        print()
        print("Arguments:")
        print("  namespace         - The namespace to modify")
        print("  tru_count        - Number of TRUs to provision")
        print("  end_time_minutes - (Optional) Minutes from now to revert to on-demand")
        print()
        print("Example:")
        print("  # Set namespace to 5 TRUs, no revert")
        print("  python run_scheduled_capacity_change.py my-namespace.abc123 5")
        print()
        print("  # Set namespace to 5 TRUs, revert to on-demand in 10 minutes")
        print("  python run_scheduled_capacity_change.py my-namespace.abc123 5 10")
        sys.exit(1)

    namespace = sys.argv[1]
    try:
        tru_count = int(sys.argv[2])
    except ValueError:
        logger.error(f"Invalid TRU count: {sys.argv[2]}")
        sys.exit(1)

    end_time = None
    if len(sys.argv) >= 4:
        try:
            end_time_minutes = int(sys.argv[3])
            end_time = datetime.utcnow() + timedelta(minutes=end_time_minutes)
            logger.info(f"End time set to {end_time} ({end_time_minutes} minutes from now)")
        except ValueError:
            logger.error(f"Invalid end time minutes: {sys.argv[3]}")
            sys.exit(1)

    logger.info("=" * 80)
    logger.info("Scheduled Capacity Change Workflow Execution")
    logger.info("=" * 80)
    logger.info(f"Namespace: {namespace}")
    logger.info(f"TRU Count: {tru_count}")
    logger.info(f"End Time: {end_time if end_time else 'Not set (no revert)'}")
    logger.info(f"Dry run mode: {settings.dry_run_mode}")
    logger.info("=" * 80)

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

    # Create workflow input
    workflow_input = ScheduledCapacityChangeInput(
        namespace=namespace,
        desired_trus=tru_count,
        end_time=end_time,
    )

    # Execute workflow
    try:
        logger.info("Starting workflow execution...")
        logger.info(f"Input: {workflow_input}")
        
        result = await client.execute_workflow(
            ScheduledCapacityChangeWorkflow.run,
            workflow_input,
            id=f"scheduled-capacity-change-{namespace}-{int(datetime.now().timestamp())}",
            task_queue=settings.task_queue,
        )

        logger.info("=" * 80)
        logger.info("Workflow completed!")
        logger.info("=" * 80)
        logger.info(f"Result: {result}")
        logger.info(f"Namespace: {result.namespace}")
        logger.info(f"Initial change success: {result.initial_change_success}")
        logger.info(f"Verification success: {result.verification_success}")
        
        if result.reverted_to_on_demand:
            logger.info(f"Reverted to on-demand: {result.reverted_to_on_demand}")
            logger.info(f"Revert verification success: {result.revert_verification_success}")
        
        if result.errors:
            logger.error(f"Errors encountered ({len(result.errors)}):")
            for error in result.errors:
                logger.error(f"  - {error}")
        else:
            logger.info("✓ No errors encountered")

    except Exception as e:
        logger.error(f"Failed to execute workflow: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print()
    print("=" * 80)
    print("Temporal Cloud Scheduled Capacity Change - Manual Execution")
    print("=" * 80)
    print()
    print("This script will execute a scheduled capacity change workflow once.")
    print("Make sure the worker is running in another terminal!")
    print()
    asyncio.run(main())
