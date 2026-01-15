#!/usr/bin/env python3
"""Script to run the BulkCapacityAnalysisWorkflow once."""

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.envconfig import ClientConfig

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.workflows import BulkCapacityAnalysisWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Run the BulkCapacityAnalysisWorkflow once."""
    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Please ensure all required environment variables are set")
        sys.exit(1)

    logger.info("Bulk Capacity Analysis - Manual Execution")

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

    # Execute workflow
    try:
        logger.info("Starting BulkCapacityAnalysisWorkflow...")
        result = await client.execute_workflow(
            BulkCapacityAnalysisWorkflow.run,
            id=f"bulk-capacity-analysis-{asyncio.get_event_loop().time()}",
            task_queue=settings.task_queue,
        )

        logger.info("=" * 60)
        logger.info("Workflow completed successfully!")
        logger.info("=" * 60)
        logger.info(f"Analyzed {len(result)} namespaces:")
        logger.info("")
        
        for recommendation in result:
            logger.info(f"  {recommendation}")

    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 60)
    print("Temporal Cloud - Bulk Capacity Analysis")
    print("=" * 60)
    print()
    print("This script will execute the workflow once for testing.")
    print("Make sure the worker is running in another terminal!")
    print()
    asyncio.run(main())
