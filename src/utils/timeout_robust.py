import signal
import functools
import threading
import time
import multiprocessing
import os
from typing import Callable, Any


class TimeoutError(Exception):
    """Raised when a function times out"""
    pass


class RobustTimeoutHandler:
    """
    More robust timeout handler that uses multiple mechanisms:
    1. signal.alarm (primary)
    2. Threading timer (backup)
    3. Process watchdog (ultimate fallback)
    """

    def __init__(self, timeout_seconds: int = 300):
        self.timeout_seconds = timeout_seconds
        self.old_handler = None
        self.timer = None
        self.timed_out = False
        self.start_time = None

        # Check if signal.alarm is available (Unix-like systems only)
        if not hasattr(signal, 'alarm'):
            raise RuntimeError(
                "Timeout mechanism requires Unix-like system (Linux/macOS). "
                "signal.alarm() is not available on this platform."
            )

    def _timeout_handler(self, signum, frame):
        """Signal handler that raises TimeoutError when SIGALRM is received"""
        self.timed_out = True
        raise TimeoutError(f"Operation timed out after {self.timeout_seconds} seconds")

    def _watchdog_thread(self):
        """Watchdog thread that monitors execution time"""
        time.sleep(self.timeout_seconds + 5)  # Give 5 seconds grace period
        if not self.timed_out and self.start_time:
            elapsed = time.time() - self.start_time
            if elapsed >= self.timeout_seconds:
                print(f"\n❌ WATCHDOG TIMEOUT: Operation exceeded {elapsed:.1f} seconds")
                print("All timeout mechanisms failed, forcing immediate exit...")
                print("This usually indicates Selenium WebDriver is blocking signals")
                os._exit(1)  # Nuclear option - immediate exit

    def __enter__(self):
        """Enter the timeout context"""
        self.start_time = time.time()
        self.timed_out = False

        # Method 1: Signal-based timeout (primary)
        self.old_handler = signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.timeout_seconds)

        # Method 2: Thread-based watchdog (ultimate backup)
        self.timer = threading.Thread(target=self._watchdog_thread, daemon=True)
        self.timer.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the timeout context"""
        # Mark as completed
        self.timed_out = True

        # Cancel the alarm
        signal.alarm(0)

        # Restore the original signal handler
        if self.old_handler is not None:
            try:
                signal.signal(signal.SIGALRM, self.old_handler)
            except (ValueError, OSError):
                pass


class SimpleTimeoutHandler:
    """Simpler timeout handler using just signal.alarm"""

    def __init__(self, timeout_seconds: int = 300):
        self.timeout_seconds = timeout_seconds
        self.old_handler = None

    def _timeout_handler(self, signum, frame):
        raise TimeoutError(f"Operation timed out after {self.timeout_seconds} seconds")

    def __enter__(self):
        self.old_handler = signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.timeout_seconds)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        signal.alarm(0)
        if self.old_handler is not None:
            try:
                signal.signal(signal.SIGALRM, self.old_handler)
            except (ValueError, OSError):
                pass


# Use the robust version by default
TimeoutHandler = RobustTimeoutHandler


def with_timeout(timeout_seconds: int = 300):
    """Decorator factory for adding timeout to functions"""
    return TimeoutHandler(timeout_seconds)


def is_timeout_supported():
    """Check if timeout functionality is supported on this platform"""
    return hasattr(signal, 'alarm') and os.name != 'nt'
