"""Common utility functions shared by Revo3 Python examples."""

import asyncio
import platform
import signal

from common_imports import logger


def setup_shutdown_event(log=None):
    """Create an asyncio event that is set on SIGINT/SIGTERM."""
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    active_logger = log or logger

    def shutdown_handler():
        active_logger.info("Shutdown signal received")
        shutdown_event.set()

    if platform.system() != "Windows":
        loop.add_signal_handler(signal.SIGINT, shutdown_handler)
        loop.add_signal_handler(signal.SIGTERM, shutdown_handler)
    else:
        signal.signal(signal.SIGINT, lambda _signal, _frame: shutdown_handler())
        signal.signal(signal.SIGTERM, lambda _signal, _frame: shutdown_handler())

    return shutdown_event
