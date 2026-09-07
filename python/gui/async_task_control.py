"""Thread-safe lifecycle control for asyncio tasks owned by GUI workers."""

import threading


class AsyncTaskControl:
    def __init__(self):
        self._loop = None
        self._task = None
        self._cancel_requested = False
        self._lock = threading.Lock()

    def start(self, loop, coroutine):
        with self._lock:
            self._loop = loop
            self._task = loop.create_task(coroutine)
            if self._cancel_requested:
                self._task.cancel()
            return self._task

    def cancel(self):
        with self._lock:
            self._cancel_requested = True
            loop = self._loop
            task = self._task
        if loop is None or task is None:
            return
        try:
            loop.call_soon_threadsafe(task.cancel)
        except RuntimeError:
            pass

    def finish(self):
        with self._lock:
            self._loop = None
            self._task = None
