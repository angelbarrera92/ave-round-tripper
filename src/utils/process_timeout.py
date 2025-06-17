import multiprocessing
import time
import signal
import os
import sys
from typing import Callable, Any


class TimeoutError(Exception):
    """Raised when a function times out"""
    pass


def _target_wrapper(func, args, kwargs, result_queue, exception_queue):
    """Wrapper function to run the target function and capture results/exceptions"""
    try:
        result = func(*args, **kwargs)
        result_queue.put(result)
    except Exception as e:
        exception_queue.put(e)


class ProcessTimeoutHandler:
    """
    Process-based timeout handler that's immune to signal blocking.
    This runs the function in a separate process and kills it if it times out.
    """

    def __init__(self, timeout_seconds: int = 180):
        self.timeout_seconds = timeout_seconds
        self.process = None
        self.result_queue = None
        self.exception_queue = None

    def run_with_timeout(self, func: Callable, *args, **kwargs) -> Any:
        """Run a function with timeout in a separate process"""

        # Create queues for communication
        self.result_queue = multiprocessing.Queue()
        self.exception_queue = multiprocessing.Queue()

        # Create and start the process
        self.process = multiprocessing.Process(
            target=_target_wrapper,
            args=(func, args, kwargs, self.result_queue, self.exception_queue)
        )

        print(f"🚀 Starting process with {self.timeout_seconds}s timeout...")
        start_time = time.time()
        self.process.start()

        # Wait for the process to complete or timeout
        self.process.join(timeout=self.timeout_seconds)

        if self.process.is_alive():
            # Process is still running - kill it
            elapsed = time.time() - start_time
            print(f"💀 Process timeout after {elapsed:.1f}s - killing process...")
            self.process.terminate()
            time.sleep(1)  # Give it a moment to terminate gracefully

            if self.process.is_alive():
                print("🔥 Force killing process...")
                self.process.kill()

            self.process.join()  # Wait for cleanup
            raise TimeoutError(f"Operation timed out after {self.timeout_seconds} seconds")

        # Check for exceptions
        if not self.exception_queue.empty():
            exception = self.exception_queue.get()
            raise exception

        # Get the result
        if not self.result_queue.empty():
            return self.result_queue.get()
        else:
            raise RuntimeError("Process completed but no result was returned")


# For backward compatibility, create a simple wrapper
class TimeoutHandler:
    """Simple timeout handler using process isolation"""

    def __init__(self, timeout_seconds: int = 180):
        self.timeout_seconds = timeout_seconds
        self.handler = ProcessTimeoutHandler(timeout_seconds)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def run_with_timeout(self, func: Callable, *args, **kwargs) -> Any:
        return self.handler.run_with_timeout(func, *args, **kwargs)


def is_timeout_supported():
    """Check if timeout functionality is supported on this platform"""
    return True  # Process-based timeout works on all platforms


# Test function
def test_timeout():
    """Test the timeout mechanism"""
    def slow_function():
        print("Starting slow operation...")
        time.sleep(10)
        return "Should not complete"

    def fast_function():
        print("Starting fast operation...")
        time.sleep(1)
        return "Completed successfully"

    handler = ProcessTimeoutHandler(3)

    # Test timeout
    try:
        result = handler.run_with_timeout(slow_function)
        print(f"ERROR: {result}")
    except TimeoutError as e:
        print(f"SUCCESS: {e}")

    # Test normal completion
    try:
        result = handler.run_with_timeout(fast_function)
        print(f"SUCCESS: {result}")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    test_timeout()
