import signal
import threading
import time
import os
import sys
import subprocess
from typing import Callable, Any


class TimeoutError(Exception):
    """Raised when a function times out"""
    pass


class AggressiveTimeoutHandler:
    """
    Extremely aggressive timeout handler that WILL terminate the process.
    Uses multiple escalating mechanisms to ensure timeout is enforced.
    """

    def __init__(self, timeout_seconds: int = 120):
        self.timeout_seconds = timeout_seconds
        self.old_handler = None
        self.start_time = None
        self.completed = False
        self.pid = os.getpid()

        if not hasattr(signal, 'alarm'):
            raise RuntimeError("Requires Unix-like system")

    def _save_timeout_flag(self):
        """Save a flag indicating timeout occurred"""
        try:
            with open('.timeout_occurred', 'w') as f:
                f.write(f"{int(time.time())},{self.pid},{self.timeout_seconds}")
        except:
            pass

    def _force_kill_browsers(self):
        """Force kill all Chrome/WebDriver processes with improved targeting"""
        try:
            # Save PIDs of processes we find first
            chrome_pids = []
            webdriver_pids = []
            
            try:
                # Find Chrome processes launched by this specific process
                result = subprocess.run(['pgrep', '-f', 'chrome.*--headless'], capture_output=True, text=True)
                if result.stdout.strip():
                    chrome_pids = result.stdout.strip().split('\n')
                    print(f"📋 Found headless Chrome processes: {', '.join(chrome_pids)}")
                
                # Find chromedriver processes
                result = subprocess.run(['pgrep', '-f', 'chromedriver'], capture_output=True, text=True)
                if result.stdout.strip():
                    webdriver_pids = result.stdout.strip().split('\n')
                    print(f"📋 Found ChromeDriver processes: {', '.join(webdriver_pids)}")
                    
                if not chrome_pids and not webdriver_pids:
                    print("ℹ️ No browser processes found to kill")
                    return
                    
            except Exception as e:
                print(f"⚠️ Error detecting browser processes: {e}")
                # Fallback to general approach
                chrome_pids = []
                webdriver_pids = []

            # Step 1: Try SIGTERM first (graceful shutdown)
            all_pids = chrome_pids + webdriver_pids
            if all_pids:
                print(f"🔄 Sending SIGTERM to {len(all_pids)} browser processes...")
                for pid in all_pids:
                    try:
                        subprocess.run(['kill', '-TERM', pid], check=False, capture_output=True)
                    except:
                        pass
                
                # Wait for graceful shutdown
                time.sleep(3)

            # Step 2: Check what's still running and use SIGKILL
            still_running = []
            for pid in all_pids:
                try:
                    # Check if process still exists
                    subprocess.run(['kill', '-0', pid], check=True, capture_output=True)
                    still_running.append(pid)
                except subprocess.CalledProcessError:
                    # Process doesn't exist anymore
                    pass
            
            if still_running:
                print(f"💀 Force killing {len(still_running)} stubborn processes with SIGKILL...")
                for pid in still_running:
                    try:
                        subprocess.run(['kill', '-9', pid], check=False, capture_output=True)
                    except:
                        pass
                        
                # Final wait
                time.sleep(2)
            
            # Step 3: Fallback to pkill if specific PIDs didn't work
            try:
                subprocess.run(['pkill', '-9', '-f', 'chrome.*--headless'], check=False, capture_output=True)
                subprocess.run(['pkill', '-9', '-f', 'chromedriver'], check=False, capture_output=True)
                print("🔥 Used pkill as fallback for any remaining processes")
            except:
                pass

            # Final verification
            try:
                result = subprocess.run(['pgrep', '-f', 'chrome.*--headless'], capture_output=True, text=True)
                if result.stdout.strip():
                    remaining = result.stdout.strip().replace('\n', ', ')
                    print(f"⚠️ Some browser processes still running: {remaining}")
                else:
                    print("✅ All browser processes successfully terminated")
            except:
                print("✅ Browser process cleanup completed")
                
        except Exception as e:
            print(f"⚠️ Error in browser cleanup: {e}")
            # Last resort - nuclear option
            try:
                subprocess.run(['killall', '-9', 'Google Chrome'], check=False, capture_output=True, timeout=5)
                subprocess.run(['killall', '-9', 'chrome'], check=False, capture_output=True, timeout=5)
                subprocess.run(['killall', '-9', 'chromedriver'], check=False, capture_output=True, timeout=5)
                print("🔥 Used killall as nuclear fallback")
            except:
                print("⚠️ All browser killing attempts exhausted")
                pass

    def _signal_handler(self, signum, frame):
        """Primary timeout via signal - immediate exception"""
        if not self.completed:
            elapsed = time.time() - self.start_time if self.start_time else self.timeout_seconds
            print(f"\n🚨 SIGNAL TIMEOUT: Operation exceeded {elapsed:.1f} seconds")
            print("💀 Terminating via signal handler...")
            print("🔥 Force killing all Chrome/WebDriver processes...")
            self.completed = True
            self._save_timeout_flag()
            self._force_kill_browsers()
            raise TimeoutError(f"Operation timed out after {elapsed:.1f} seconds")

    def _watchdog_thread(self):
        """Watchdog thread - sends SIGTERM after timeout + 5 seconds"""
        time.sleep(self.timeout_seconds + 5)
        if not self.completed:
            elapsed = time.time() - self.start_time if self.start_time else self.timeout_seconds + 5
            print(f"\n⚠️  WATCHDOG: Signal timeout failed after {elapsed:.1f}s")
            print("📡 Sending SIGTERM to process...")
            print("🔥 Force killing browsers again...")
            self._save_timeout_flag()
            self._force_kill_browsers()
            try:
                os.kill(self.pid, signal.SIGTERM)
            except:
                pass

    def _killer_thread(self):
        """Nuclear option - SIGKILL after timeout + 10 seconds"""
        time.sleep(self.timeout_seconds + 10)
        if not self.completed:
            elapsed = time.time() - self.start_time if self.start_time else self.timeout_seconds + 10
            print(f"\n💀 KILLER: SIGTERM failed after {elapsed:.1f}s")
            print("🔥 Sending SIGKILL - immediate termination...")
            print("💣 Final browser cleanup...")
            self._save_timeout_flag()
            self._force_kill_browsers()
            try:
                os.kill(self.pid, signal.SIGKILL)
            except:
                pass
            # If SIGKILL somehow fails, use os._exit as absolute last resort
            time.sleep(2)
            if not self.completed:
                print("💣 EMERGENCY: Using os._exit(1)")
                os._exit(1)

    def _emergency_thread(self):
        """Absolute last resort - os._exit after timeout + 15 seconds"""
        time.sleep(self.timeout_seconds + 15)
        if not self.completed:
            print(f"\n💣 EMERGENCY SHUTDOWN: All termination methods failed")
            print("🚨 Process is completely stuck - forcing immediate exit")
            self._save_timeout_flag()
            os._exit(1)

    def __enter__(self):
        """Enter timeout context with escalating protection"""
        self.start_time = time.time()
        self.completed = False
        self.pid = os.getpid()

        print(f"🕐 Starting aggressive timeout protection: {self.timeout_seconds}s (PID: {self.pid})")
        print("🔥 Enhanced browser process killing enabled")

        # Method 1: Signal alarm (primary - immediate exception)
        self.old_handler = signal.signal(signal.SIGALRM, self._signal_handler)
        signal.alarm(self.timeout_seconds)

        # Method 2: Watchdog thread (SIGTERM after +5s)
        threading.Thread(target=self._watchdog_thread, daemon=True).start()

        # Method 3: Killer thread (SIGKILL after +10s)
        threading.Thread(target=self._killer_thread, daemon=True).start()

        # Method 4: Emergency thread (os._exit after +15s)
        threading.Thread(target=self._emergency_thread, daemon=True).start()

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


def check_timeout_recovery():
    """Check if previous run timed out and provide recovery info"""
    try:
        if os.path.exists('.timeout_occurred'):
            with open('.timeout_occurred', 'r') as f:
                data = f.read().strip().split(',')
                if len(data) >= 3:
                    timestamp, pid, timeout = data[:3]
                    time_ago = int(time.time()) - int(timestamp)
                    print(f"⚠️  Previous timeout detected:")
                    print(f"   - PID: {pid}")
                    print(f"   - Timeout: {timeout}s")
                    print(f"   - Time ago: {time_ago}s")
                    if time_ago < 300:  # Less than 5 minutes ago
                        print("🚨 Recent timeout - process may have been stuck!")
            os.remove('.timeout_occurred')
            return True
    except:
        pass
    return False


if __name__ == "__main__":
    # Test the timeout mechanism
    def test_function():
        print("Starting test...")
        time.sleep(5)
        print("Test completed")

    def stuck_function():
        print("Starting stuck operation...")
        time.sleep(200)  # This should timeout
        print("This should never print")

    # Test normal operation
    print("=== Testing normal operation ===")
    try:
        with TimeoutHandler(10):
            test_function()
    except TimeoutError as e:
        print(f"Unexpected timeout: {e}")

    # Test timeout operation
    print("\n=== Testing timeout operation ===")
    try:
        with TimeoutHandler(3):
            stuck_function()
    except TimeoutError as e:
        print(f"Expected timeout: {e}")

    print("\nTest completed")
