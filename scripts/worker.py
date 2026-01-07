"""Worker script to run capacity management workflows and activities."""

import asyncio
import logging
import sys
from pathlib import Path

from temporalio.client import Client, TLSConfig
from temporalio.worker import Worker

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.activities import (
    check_throttling,
    disable_provisioning,
    enable_provisioning,
    list_namespaces,
    send_slack_notification,
)
from src.config import get_settings
from src.workflows import CapacityManagementWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Start the worker to process capacity management workflows."""
    # Load settings
    try:
        settings = get_settings()
        settings.validate_auth_config()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Please ensure all required environment variables are set")
        sys.exit(1)

    logger.info(f"Starting worker for namespace: {settings.temporal_namespace}")
    logger.info(f"Task queue: {settings.task_queue}")
    logger.info(f"Dry run mode: {settings.dry_run_mode}")
    
    # Determine authentication method
    if settings.use_api_key_auth():
        logger.info("Using API key authentication")
    else:
        logger.info("Using mTLS certificate authentication")

    # Configure authentication
    try:
        if settings.use_api_key_auth():
            # Use API key authentication
            client = await Client.connect(
                settings.temporal_address,
                namespace=settings.temporal_namespace,
                api_key=settings.temporal_api_key,
            )
        else:
            # Use mTLS authentication
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

    # Create and run worker
    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[CapacityManagementWorkflow],
        activities=[
            check_throttling,
            disable_provisioning,
            enable_provisioning,
            list_namespaces,
            send_slack_notification,
        ],
    )

    logger.info("Worker started, waiting for tasks...")
    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Worker shutting down...")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
