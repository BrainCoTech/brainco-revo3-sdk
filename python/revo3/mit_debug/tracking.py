"""Compatibility entry point for the Revo3 2.x MIT trajectory example."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mit_control import parse_args, run


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
