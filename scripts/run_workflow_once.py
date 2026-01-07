"""Script to manually execute the capacity management workflow once (for testing)."""

import asyncio
import logging
import sys
from pathlib import Path

from temporalio.client import Client, TLSConfig

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.workflows.capacity_management import (
    CapacityManagementWorkflow,
    CapacityManagementInput,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Manually execute the capacity management workflow once."""
    # Load settings
    try:
        settings = get_settings()
        settings.validate_auth_config()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Please ensure all required environment variables are set")
        sys.exit(1)

    logger.info("Manual workflow execution")
    logger.info(f"Namespace: {settings.temporal_namespace}")
    logger.info(f"Dry run mode: {settings.dry_run_mode}")

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

    # Create workflow input
    workflow_input = CapacityManagementInput(
        default_tru_count=settings.default_tru_count,
        min_actions_threshold=settings.min_actions_threshold,
        dry_run=settings.dry_run_mode,
    )

    # Execute workflow
    try:
        logger.info("Starting workflow execution...")
        result = await client.execute_workflow(
            CapacityManagementWorkflow.run,
            workflow_input,
            id=f"capacity-management-manual-{asyncio.get_event_loop().time()}",
            task_queue=settings.task_queue,
        )

        logger.info("=" * 60)
        logger.info("Workflow completed successfully!")
        logger.info("=" * 60)
        logger.info(f"Result: {result}")
        logger.info(f"Total namespaces checked: {result.total_namespaces_checked}")
        logger.info(f"Namespaces enabled: {len(result.namespaces_enabled)}")
        if result.namespaces_enabled:
            for ns in result.namespaces_enabled:
                logger.info(f"  - {ns}")
        logger.info(f"Namespaces disabled: {len(result.namespaces_disabled)}")
        if result.namespaces_disabled:
            for ns in result.namespaces_disabled:
                logger.info(f"  - {ns}")
        logger.info(f"Errors: {len(result.errors)}")
        if result.errors:
            for error in result.errors:
                logger.error(f"  - {error}")
        
        logger.info("")
        logger.info("Decisions made:")
        for decision in result.decisions:
            logger.info(f"  {decision}")

    except Exception as e:
        logger.error(f"Failed to execute workflow: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 60)
    print("Temporal Cloud Capacity Management - Manual Execution")
    print("=" * 60)
    print()
    print("This script will execute the workflow once for testing.")
    print("Make sure the worker is running in another terminal!")
    print()
    asyncio.run(main())
