"""Check GitHub for a newer Inkwell and install it with the checkout's update.sh.

`make install` writes an install-info file next to the installed package that
records the git checkout it came from, the commit it installed and the
install prefix. Inkwell run straight from a checkout uses that checkout.
Updating only touches the checkout and the installed program, never notes.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

from gi.repository import Gio, GLib

PACKAGE_DIR = Path(__file__).resolve().parent
INFO_FILE = "install-info"
BRANCH = "main"


@dataclass
class Install:
    source: Path
    commit: str | None = None
    prefix: str | None = None


def is_checkout(path):
    return (path / ".git").exists() and (path / "update.sh").is_file()


def read_install_info(path):
    info = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return info
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and value.strip():
            info[key.strip()] = value.strip()
    return info


def find_install(package_dir=PACKAGE_DIR):
    """Where this copy of Inkwell can be updated from, or None."""
    package_dir = Path(package_dir)
    if is_checkout(package_dir.parent):
        return Install(source=package_dir.parent)
    info = read_install_info(package_dir.parent / INFO_FILE)
    source = info.get("source")
    if not source or not is_checkout(Path(source)):
        return None
    return Install(source=Path(source), commit=info.get("commit"), prefix=info.get("prefix"))


def describe_error(output, source):
    """A short, readable reason from git or update.sh output."""
    lowered = output.lower()
    if "could not read username" in lowered or "authentication failed" in lowered:
        return (
            "GitHub asked for a sign-in. Run “git pull” once in a terminal in "
            f"{source} so git remembers it, then try again."
        )
    if "could not resolve host" in lowered or "unable to access" in lowered:
        return "Could not reach GitHub. Check your internet connection and try again."
    if "not possible to fast-forward" in lowered or "diverging" in lowered:
        return f"The checkout in {source} has its own changes, so it can't be updated automatically."
    if "would be overwritten" in lowered or "please commit your changes" in lowered:
        return f"The checkout in {source} has unsaved edits to Inkwell's files. Commit or undo them first."
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else "Something went wrong."


class Updater:
    UNAVAILABLE = "unavailable"
    IDLE = "idle"
    CHECKING = "checking"
    UP_TO_DATE = "up-to-date"
    AVAILABLE = "available"
    UPDATING = "updating"
    UPDATED = "updated"
    FAILED = "failed"

    def __init__(self, install=None):
        self.install = install
        self.state = self.IDLE if install else self.UNAVAILABLE
        self.message = ""
        self.new_commits = []
        self._listeners = []

    @property
    def busy(self):
        return self.state in (self.CHECKING, self.UPDATING)

    def connect(self, callback):
        self._listeners.append(callback)

    def disconnect(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _set_state(self, state, message=""):
        self.state = state
        self.message = message
        for callback in list(self._listeners):
            callback(self)

    def check(self):
        if not self.install or self.busy:
            return
        self._set_state(self.CHECKING)
        self._run(["git", "fetch", "--quiet", "origin", BRANCH], self._on_fetched)

    def _on_fetched(self, ok, output):
        if not ok:
            self._set_state(self.FAILED, describe_error(output, self.install.source))
            return
        base = self.install.commit or "HEAD"
        self._run(
            ["git", "log", "--format=%s", f"{base}..origin/{BRANCH}"],
            lambda ok, out: self._on_logged(ok, out, base),
        )

    def _on_logged(self, ok, output, base):
        if not ok and base != "HEAD":
            # The recorded commit isn't in this checkout; compare with it instead.
            self._on_logged_retry()
            return
        if not ok:
            self._set_state(self.FAILED, describe_error(output, self.install.source))
            return
        self.new_commits = [line for line in output.splitlines() if line.strip()]
        self._set_state(self.AVAILABLE if self.new_commits else self.UP_TO_DATE)

    def _on_logged_retry(self):
        self._run(
            ["git", "log", "--format=%s", f"HEAD..origin/{BRANCH}"],
            lambda ok, out: self._on_logged(ok, out, "HEAD"),
        )

    def update(self):
        if not self.install or self.busy:
            return
        self._set_state(self.UPDATING)
        env = {}
        if self.install.prefix:
            env["INKWELL_PREFIX"] = self.install.prefix
        self._run(["sh", str(self.install.source / "update.sh")], self._on_updated, env)

    def _on_updated(self, ok, output):
        if not ok:
            self._set_state(self.FAILED, describe_error(output, self.install.source))
            return
        self.install = find_install() or self.install
        self.new_commits = []
        self._set_state(self.UPDATED)

    def _run(self, argv, callback, env=None):
        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
        )
        launcher.set_cwd(str(self.install.source))
        # Never wait on a password prompt in a terminal nobody can see.
        launcher.setenv("GIT_TERMINAL_PROMPT", "0", True)
        launcher.setenv("LC_ALL", "C", True)
        for key, value in (env or {}).items():
            launcher.setenv(key, value, True)
        try:
            process = launcher.spawnv(argv)
        except GLib.Error as error:
            GLib.idle_add(lambda: callback(False, error.message) and False)
            return

        def on_done(proc, result):
            try:
                _ok, stdout, _stderr = proc.communicate_utf8_finish(result)
            except GLib.Error as error:
                callback(False, error.message)
                return
            callback(proc.get_successful(), stdout or "")

        process.communicate_utf8_async(None, None, on_done)


def restart_command(argv):
    """The command that starts this Inkwell again with the same arguments."""
    return [sys.executable, "-m", "inkwell", *argv[1:]]
