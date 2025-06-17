import subprocess
import time
import signal
import os
import threading
from typing import Callable, Any


class TimeoutError(Exception):
    """Raised when a function times out"""
    pass


class HybridTimeoutHandler:
    """
    Hybrid timeout handler that uses multiple mechanisms:
    1. signal.alarm (primary)
    2. Threading with forced exit (backup)
    """

    def __init__(self, timeout_seconds: int = 180):
        self.timeout_seconds = timeout_seconds
        self.old_handler = None
        self.timed_out = False
        self.start_time = None

        # Check if signal.alarm is available
        if not hasattr(signal, 'alarm'):
            raise RuntimeError("Timeout mechanism requires Unix-like system")

    def _timeout_handler(self, signum, frame):
        """Signal handler that raises TimeoutError"""
        self.timed_out = True
        raise TimeoutError(f"Operation timed out after {self.timeout_seconds} seconds")

    def _force_exit_thread(self):
        """Thread that forces program exit if signal fails"""
        time.sleep(self.timeout_seconds + 10)  # Give 10 seconds grace period
        if not self.timed_out and self.start_time:
            elapsed = time.time() - self.start_time
            if elapsed >= self.timeout_seconds:
                print(f"\n💀 FORCE EXIT: Signal timeout failed after {elapsed:.1f}s")
                print("🚨 Selenium likely blocked signals - forcing immediate exit")
                os._exit(1)  # Nuclear option

    def __enter__(self):
        """Enter the timeout context"""
        self.start_time = time.time()
        self.timed_out = False

        # Set up signal handler
        self.old_handler = signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.timeout_seconds)

        # Start backup thread
        thread = threading.Thread(target=self._force_exit_thread, daemon=True)
        thread.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the timeout context"""
        self.timed_out = True  # Stop the backup thread
        signal.alarm(0)  # Cancel alarm

        # Restore signal handler
        if self.old_handler is not None:
            try:
                signal.signal(signal.SIGALRM, self.old_handler)
            except (ValueError, OSError):
                pass


# Use the hybrid handler
TimeoutHandler = HybridTimeoutHandler


def is_timeout_supported():
    """Check if timeout functionality is supported"""
    return hasattr(signal, 'alarm') and os.name != 'nt'


def test_timeout():
    """Test the timeout mechanism"""
    print("Testing hybrid timeout mechanism...")

    # Test 1: Normal operation
    try:
        with TimeoutHandler(5):
            print("Test 1: Starting short operation...")
            time.sleep(1)
            print("✅ Test 1: Completed normally")
    except TimeoutError:
        print("❌ Test 1: Unexpected timeout")

    # Test 2: Timeout operation
    try:
        with TimeoutHandler(3):
            print("Test 2: Starting long operation...")
            time.sleep(10)
            print("❌ Test 2: Should not reach here")
    except TimeoutError as e:
        print(f"✅ Test 2: {e}")

    print("All tests completed")


if __name__ == "__main__":
    test_timeout()
