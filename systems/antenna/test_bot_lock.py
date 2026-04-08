"""
Test that only one bot instance can run at a time via PID lockfile.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

LOCK_FILE = Path(__file__).parent / ".bot.lock"


def cleanup():
    """Remove lock file if it exists."""
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


def test_acquire_lock_succeeds_when_no_lock():
    """First instance should acquire lock successfully."""
    cleanup()
    from bot import acquire_lock, release_lock
    assert acquire_lock() is True
    assert LOCK_FILE.exists()
    pid = int(LOCK_FILE.read_text().strip())
    assert pid == os.getpid()
    release_lock()
    assert not LOCK_FILE.exists()


def test_acquire_lock_fails_when_already_locked():
    """Second instance should fail when lock is held by a live process."""
    cleanup()
    # Write current PID (alive) to lock file
    LOCK_FILE.write_text(str(os.getpid()))
    from bot import acquire_lock
    assert acquire_lock() is False
    cleanup()


def test_acquire_lock_clears_stale_lock():
    """Lock should be acquired if the old PID is dead (stale lock)."""
    cleanup()
    # Write a PID that doesn't exist
    LOCK_FILE.write_text("99999999")
    from bot import acquire_lock, release_lock
    assert acquire_lock() is True
    release_lock()


def test_second_bot_process_exits():
    """Launching bot.py while lock is held should exit with code 1."""
    cleanup()
    # Write current PID to simulate a running instance
    LOCK_FILE.write_text(str(os.getpid()))

    bot_path = Path(__file__).parent / "bot.py"
    result = subprocess.run(
        [sys.executable, str(bot_path)],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "ANTENNA_BOT_TOKEN": "fake_token_for_test"}
    )
    assert result.returncode == 1
    assert "Another Antenna bot instance is already running" in result.stdout
    cleanup()


if __name__ == "__main__":
    tests = [
        test_acquire_lock_succeeds_when_no_lock,
        test_acquire_lock_fails_when_already_locked,
        test_acquire_lock_clears_stale_lock,
        test_second_bot_process_exits,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS: {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__} — {e}")
        finally:
            cleanup()

    print(f"\n{passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
