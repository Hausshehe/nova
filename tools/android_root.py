"""Reliable privileged Android command execution for Nova."""

import os
import signal
import subprocess


DEFAULT_TIMEOUT_SECONDS = 15


def run_root(command, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Run a command through an interactive root shell with a hard timeout.

    Nova uses an interactive `su` shell because `su -c` has been unreliable on
    this device for some Android services.  The shell is started in its own
    process group so a stuck child such as `uiautomator` cannot survive the
    timeout and leave the planner waiting forever.
    """
    process = subprocess.Popen(
        ["su"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    try:
        stdout, stderr = process.communicate(
            command + "\nexit\n",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                process.kill()
            except ProcessLookupError:
                pass

        stdout, stderr = process.communicate()
        return subprocess.CompletedProcess(
            args=command,
            returncode=124,
            stdout=stdout or "",
            stderr=(stderr or "") + f"\nCommand timed out after {timeout} seconds.",
        )

    return subprocess.CompletedProcess(
        args=command,
        returncode=process.returncode,
        stdout=stdout or "",
        stderr=stderr or "",
    )
