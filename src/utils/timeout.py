import signal
import functools
import threading
import time
import os
from typing import Callable, Any
import sys


class TimeoutError(Exception):
    """Raised when a function times out"""
    pass


class AggressiveTimeoutHandler:
    """
    Extremely aggressive timeout handler that WILL terminate the process.
    Uses both signal and threading mechanisms to ensure timeout is enforced.
    """

    def __init__(self, timeout_seconds: int = 180):
        self.timeout_seconds = timeout_seconds
        self.old_handler = None
        self.start_time = None
        self.completed = False

        if not hasattr(signal, 'alarm'):
            raise RuntimeError("Requires Unix-like system")

    def _save_timeout_flag(self):
        """Save a flag indicating timeout occurred for recovery detection"""
        try:
            with open('.timeout_occurred', 'w') as f:
                f.write(str(int(time.time())))
        except:
            pass  # Don't fail the timeout process if flag save fails

    def _signal_handler(self, signum, frame):
        """Primary timeout via signal"""
        if not self.completed:
            print(f"\n🚨 SIGNAL TIMEOUT: Operation exceeded {self.timeout_seconds} seconds")
            print("💀 Terminating via signal handler...")
            self.completed = True
            # Save timeout flag for recovery detection
            self._save_timeout_flag()
            raise TimeoutError(f"Operation timed out after {self.timeout_seconds} seconds")

    def _killer_thread(self):
        """Backup thread that kills the process if signal fails - ONLY for truly stuck operations"""
        time.sleep(self.timeout_seconds + 30)  # Give 30 seconds grace period
        if not self.completed:
            elapsed = time.time() - self.start_time if self.start_time else self.timeout_seconds
            print(f"\n💀 EMERGENCY KILLER: Operation truly stuck after {elapsed:.1f}s")
            print("🔥 Selenium/WebDriver completely unresponsive")
            print("💣 EMERGENCY TERMINATION TO PREVENT INFINITE HANG...")
            print("🔄 Restart the program manually")
            # Save timeout flag for recovery detection
            self._save_timeout_flag()
            os._exit(1)  # Nuclear option - only for truly stuck operations

    def _watchdog_thread(self):
        """Secondary watchdog with shorter timeout"""
        time.sleep(self.timeout_seconds)
        if not self.completed:
            elapsed = time.time() - self.start_time if self.start_time else self.timeout_seconds
            print(f"\n⏰ WATCHDOG: {elapsed:.1f}s elapsed, sending SIGTERM...")
            # Save timeout flag for recovery detection
            self._save_timeout_flag()
            try:
                os.kill(os.getpid(), signal.SIGTERM)
            except:
                pass

    def __enter__(self):
        """Enter timeout context with triple protection"""
        self.start_time = time.time()
        self.completed = False

        print(f"🕐 Starting timeout protection: {self.timeout_seconds}s")

        # Method 1: Signal alarm (primary)
        self.old_handler = signal.signal(signal.SIGALRM, self._signal_handler)
        signal.alarm(self.timeout_seconds)

        # Method 2: Watchdog thread (backup)
        threading.Thread(target=self._watchdog_thread, daemon=True).start()

        # Method 3: Killer thread (nuclear option)
        threading.Thread(target=self._killer_thread, daemon=True).start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit timeout context"""
        self.completed = True
        signal.alarm(0)  # Cancel alarm

        if self.old_handler is not None:
            try:
                signal.signal(signal.SIGALRM, self.old_handler)
            except:
                pass

        if self.start_time:
            elapsed = time.time() - self.start_time
            print(f"✅ Timeout protection completed after {elapsed:.1f}s")


# Use the aggressive handler
TimeoutHandler = AggressiveTimeoutHandler


def is_timeout_supported():
    """Check if timeout is supported"""
    return hasattr(signal, 'alarm') and os.name != 'nt'
