"""Reusable persistent root-shell execution for Nova's Android capabilities."""

import atexit
import subprocess
import threading


class RootShell:
    """Keep one interactive `su` process alive and execute commands through it."""

    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._counter = 0

    def _start(self):
        self._process = subprocess.Popen(
            ["su"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        result = self._execute_locked("id")
        if result.returncode != 0 or "uid=0" not in result.stdout:
            self.close()
            raise RuntimeError(
                "Nova could not establish a root shell: "
                + (result.stderr.strip() or result.stdout.strip() or "not root")
            )

    def _ensure_started(self):
        if self._process is None or self._process.poll() is not None:
            self._start()

    def _execute_locked(self, command):
        self._counter += 1
        marker = f"__NOVA_DONE_{self._counter}__"
        wrapped = f"{command}\nprintf '%s\\n' '{marker}'\n"

        self._process.stdin.write(wrapped)
        self._process.stdin.flush()

        stdout_lines = []
        while True:
            line = self._process.stdout.readline()
            if line == "":
                raise RuntimeError("Nova's root shell closed unexpectedly.")
            line = line.rstrip("\n")
            if line == marker:
                break
            stdout_lines.append(line)

        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="\n".join(stdout_lines),
            stderr="",
        )

    def run(self, command):
        """Execute one shell command as root and return a CompletedProcess-like result."""
        with self._lock:
            self._ensure_started()
            return self._execute_locked(command)

    def close(self):
        process = self._process
        self._process = None
        if process is None:
            return

        try:
            if process.stdin:
                process.stdin.write("exit\n")
                process.stdin.flush()
        except Exception:
            pass

        try:
            process.terminate()
        except Exception:
            pass


_shell = RootShell()
atexit.register(_shell.close)


def run_root(command):
    """Run a command through Nova's reusable interactive root shell."""
    return _shell.run(command)
