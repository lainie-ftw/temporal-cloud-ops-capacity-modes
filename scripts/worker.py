"""Worker script to run capacity management workflows and activities."""

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.envconfig import ClientConfig
from temporalio.worker import Worker

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.activities import (
    check_throttling,
    disable_provisioning,
    enable_provisioning,
    get_all_namespace_metrics,
    list_namespaces,
    send_slack_notification,
    verify_namespace_capacity,
)
from src.config import get_settings
from src.workflows import (
    BulkCapacityAnalysisWorkflow,
    CapacityManagementWorkflow,
    ScheduledCapacityChangeWorkflow,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Start the worker to process capacity management workflows."""
    # Load settings for application configuration
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Please ensure all required environment variables are set")
        sys.exit(1)

    logger.info(f"Task queue: {settings.task_queue}")
    logger.info(f"Dry run mode: {settings.dry_run_mode}")

    # Connect to Temporal using environment configuration
    # This automatically loads connection settings from environment variables:
    # - TEMPORAL_ADDRESS (or TEMPORAL_HOST_URL)
    # - TEMPORAL_NAMESPACE
    # - TEMPORAL_API_KEY (for API key authentication)
    # - TEMPORAL_TLS_CLIENT_CERT_PATH and TEMPORAL_TLS_CLIENT_KEY_PATH (for mTLS)
    try:
        logger.info("Loading Temporal connection configuration from environment variables...")
        connect_config = ClientConfig.load_client_connect_config()
        
        logger.info(f"Connecting to Temporal at {connect_config.get('target_host')}")
        logger.info(f"Namespace: {connect_config.get('namespace')}")
        
        client = await Client.connect(**connect_config)
        
        logger.info("Successfully connected to Temporal")
    except Exception as e:
        logger.error(f"Failed to connect to Temporal: {e}")
        logger.error("Please ensure the following environment variables are set:")
        logger.error("  - TEMPORAL_ADDRESS (e.g., namespace.account.tmprl.cloud:7233)")
        logger.error("  - TEMPORAL_NAMESPACE (e.g., namespace.account)")
        logger.error("  - Either TEMPORAL_API_KEY or both TEMPORAL_TLS_CLIENT_CERT_PATH and TEMPORAL_TLS_CLIENT_KEY_PATH")
        sys.exit(1)

    # Create and run worker
    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[
            CapacityManagementWorkflow,
            BulkCapacityAnalysisWorkflow,
            ScheduledCapacityChangeWorkflow,
        ],
        activities=[
            check_throttling,
            disable_provisioning,
            enable_provisioning,
            get_all_namespace_metrics,
            list_namespaces,
            send_slack_notification,
            verify_namespace_capacity,
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
