"""Reliable privileged Android command execution for Nova."""

import os
import signal
import subprocess
import tempfile
import time


DEFAULT_TIMEOUT_SECONDS = 15
POLL_INTERVAL_SECONDS = 0.05


def run_root(command, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Run a privileged Android command with a hard, pipe-safe timeout.

    Some Android services, especially uiautomator, can inherit stdout/stderr
    pipes and keep them open after the shell that launched them is stuck. Using
    ``communicate(timeout=...)`` in that situation can itself remain blocked.
    Redirect output to temporary files instead, poll the shell directly, and
    kill the entire process group when the deadline is reached.
    """
    command = str(command or "").strip()
    if not command:
        return subprocess.CompletedProcess(
            args=["su"],
            returncode=0,
            stdout="",
            stderr="",
        )

    stdout_path = None
    stderr_path = None
    process = None

    try:
        stdout_file = tempfile.NamedTemporaryFile(mode="w+b", delete=False)
        stderr_file = tempfile.NamedTemporaryFile(mode="w+b", delete=False)
        stdout_path = stdout_file.name
        stderr_path = stderr_file.name
        stdout_file.close()
        stderr_file.close()

        with open(stdout_path, "wb") as stdout_handle, open(stderr_path, "wb") as stderr_handle:
            process = subprocess.Popen(
                ["su"],
                stdin=subprocess.PIPE,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                start_new_session=True,
            )

            try:
                process.stdin.write(command + "\nexit\n")
                process.stdin.flush()
                process.stdin.close()
            except (BrokenPipeError, OSError):
                try:
                    if process.stdin:
                        process.stdin.close()
                except OSError:
                    pass

            deadline = time.monotonic() + float(timeout)
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(POLL_INTERVAL_SECONDS)

            timed_out = process.poll() is None
            if timed_out:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass

        with open(stdout_path, "rb") as handle:
            stdout = handle.read().decode("utf-8", errors="replace")
        with open(stderr_path, "rb") as handle:
            stderr = handle.read().decode("utf-8", errors="replace")

        if timed_out:
            return subprocess.CompletedProcess(
                args=["su"],
                returncode=124,
                stdout=stdout,
                stderr=f"Command timed out after {timeout} seconds.",
            )

        return subprocess.CompletedProcess(
            args=["su"],
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    finally:
        for path in (stdout_path, stderr_path):
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
