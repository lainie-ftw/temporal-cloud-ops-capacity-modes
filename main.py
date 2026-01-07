"""Main entry point for the capacity management automation.

This is a convenience script that runs the worker.
For production use, use scripts/worker.py directly.
"""

import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.worker import main
import asyncio


if __name__ == "__main__":
    print("Starting Temporal Cloud Capacity Management Worker...")
    print("For more options, use scripts/worker.py directly")
    print()
    asyncio.run(main())
