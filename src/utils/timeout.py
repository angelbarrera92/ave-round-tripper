import signal
import functools
from typing import Callable, Any
import sys
import os


class TimeoutError(Exception):
    """Raised when a function times out"""
    pass


class TimeoutHandler:
    """Context manager and decorator for handling function timeouts"""

    def __init__(self, timeout_seconds: int = 300):  # Default 5 minutes
        self.timeout_seconds = timeout_seconds
        self.old_handler = None

        # Check if signal.alarm is available (Unix-like systems only)
        if not hasattr(signal, 'alarm'):
            raise RuntimeError(
                "Timeout mechanism requires Unix-like system (Linux/macOS). "
                "signal.alarm() is not available on this platform."
            )

    def _timeout_handler(self, signum, frame):
        """Signal handler that raises TimeoutError when SIGALRM is received"""
        raise TimeoutError(f"Operation timed out after {self.timeout_seconds} seconds")

    def __enter__(self):
        """Enter the timeout context"""
        # Set up the signal handler
        self.old_handler = signal.signal(signal.SIGALRM, self._timeout_handler)
        # Start the alarm
        signal.alarm(self.timeout_seconds)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the timeout context"""
        # Cancel the alarm
        signal.alarm(0)
        # Restore the original signal handler
        if self.old_handler is not None:
            try:
                signal.signal(signal.SIGALRM, self.old_handler)
            except (ValueError, OSError):
                # In case of issues restoring the signal handler, log but don't crash
                pass

    def __call__(self, func: Callable) -> Callable:
        """Decorator version of the timeout handler"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with TimeoutHandler(self.timeout_seconds):
                return func(*args, **kwargs)
        return wrapper


def with_timeout(timeout_seconds: int = 300):
    """Decorator factory for adding timeout to functions

    Args:
        timeout_seconds: Maximum time allowed for function execution

    Usage:
        @with_timeout(180)  # 3 minutes timeout
        def my_function():
            # Function that might hang
            pass
    """
    return TimeoutHandler(timeout_seconds)


def is_timeout_supported():
    """Check if timeout functionality is supported on this platform"""
    return hasattr(signal, 'alarm') and os.name != 'nt'
