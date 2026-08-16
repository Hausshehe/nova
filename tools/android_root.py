"""Reliable privileged Android command execution for Nova."""

import subprocess


DEFAULT_TIMEOUT_SECONDS = 15


def run_root(command, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Run a command through an interactive root shell and return its output.

    On this device, `su -c` can fail with Android's package-manager service,
    while an interactive `su` process works reliably. We therefore create an
    interactive `su` process for each command and use communicate(), so a
    command such as uiautomator cannot leave Nova blocked forever on readline().
    """
    process = subprocess.Popen(
        ["su"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        stdout, stderr = process.communicate(
            command + "\nexit\n",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        process.kill()
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
