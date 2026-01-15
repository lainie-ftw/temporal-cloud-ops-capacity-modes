#!/usr/bin/env python3
"""Script to run the BulkCapacityAnalysisWorkflow once."""

import asyncio
import logging
import sys
from pathlib import Path

from temporalio.client import Client, TLSConfig

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
        settings.validate_auth_config()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Please ensure all required environment variables are set")
        sys.exit(1)

    logger.info("Bulk Capacity Analysis - Manual Execution")
    logger.info(f"Namespace: {settings.temporal_namespace}")

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
