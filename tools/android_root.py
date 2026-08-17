"""Reliable privileged Android command execution for Nova."""

import os
import signal
import subprocess


DEFAULT_TIMEOUT_SECONDS = 15


def run_root(command, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Run a privileged Android command with a real process timeout.

    Prefer a direct ``su -c`` invocation so Python does not have to keep an
    interactive root shell alive while waiting for Android services such as
    uiautomator.  The subprocess is still placed in its own process group so
    a stuck child can be killed together with the command on timeout.
    """
    command = str(command or "").strip()
    if not command:
        return subprocess.CompletedProcess(
            args=["su", "-c", ""],
            returncode=0,
            stdout="",
            stderr="",
        )

    process = subprocess.Popen(
        ["su", "-c", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    try:
        stdout, stderr = process.communicate(timeout=float(timeout))
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
            args=["su", "-c", command],
            returncode=124,
            stdout=stdout or "",
            stderr=(stderr or "") + f"\nCommand timed out after {timeout} seconds.",
        )

    return subprocess.CompletedProcess(
        args=["su", "-c", command],
        returncode=process.returncode,
        stdout=stdout or "",
        stderr=stderr or "",
    )
