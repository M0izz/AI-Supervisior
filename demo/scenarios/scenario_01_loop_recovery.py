import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from demo.scenarios.killer_scenario import run_killer_scenario

if __name__ == "__main__":
    asyncio.run(run_killer_scenario())
