"""Reliable privileged Android command execution for Nova."""

import os
import signal
import subprocess


DEFAULT_TIMEOUT_SECONDS = 15


def run_root(command, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Run a privileged Android command through an interactive root shell.

    On some rooted Android/Termux setups, especially with Magisk and SELinux,
    ``su -c <cmd>`` can run the command as root but still fail when Android
    ``cmd``/``am``/``pm`` services perform Binder IPC. The characteristic
    failure is ``Failed transaction (2147483646)``.

    An interactive ``su`` session is more reliable on these devices. Feed the
    command through stdin, then explicitly exit. Keep the subprocess in its
    own process group so a stuck Android service (for example uiautomator)
    can still be terminated by the hard timeout.
    """
    command = str(command or "").strip()
    if not command:
        return subprocess.CompletedProcess(
            args=["su"],
            returncode=0,
            stdout="",
            stderr="",
        )

    process = subprocess.Popen(
        ["su"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    try:
        stdout, stderr = process.communicate(
            command + "\nexit\n",
            timeout=float(timeout),
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
            args=["su"],
            returncode=124,
            stdout=stdout or "",
            stderr=(stderr or "") + f"\nCommand timed out after {timeout} seconds.",
        )

    return subprocess.CompletedProcess(
        args=["su"],
        returncode=process.returncode,
        stdout=stdout or "",
        stderr=stderr or "",
    )
