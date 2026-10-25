import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gi.repository import GLib  # noqa: E402

from inkwell import updater  # noqa: E402
from inkwell.updater import Updater  # noqa: E402

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(repo, name, message):
    (Path(repo) / name).write_text(message)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)


class FindInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def make_checkout(self, path):
        (path / ".git").mkdir(parents=True)
        (path / "update.sh").write_text("#!/bin/sh\n")
        return path

    def test_running_from_a_checkout_uses_it(self):
        checkout = self.make_checkout(self.tmp / "src")
        (checkout / "inkwell").mkdir()
        install = updater.find_install(checkout / "inkwell")
        self.assertEqual(install.source, checkout)
        self.assertIsNone(install.commit)

    def test_installed_copy_reads_install_info(self):
        checkout = self.make_checkout(self.tmp / "src")
        lib = self.tmp / "share" / "inkwell"
        (lib / "inkwell").mkdir(parents=True)
        (lib / "install-info").write_text(
            f"source={checkout}\ncommit=abc123\nprefix={self.tmp}\n"
        )
        install = updater.find_install(lib / "inkwell")
        self.assertEqual(install.source, checkout)
        self.assertEqual(install.commit, "abc123")
        self.assertEqual(install.prefix, str(self.tmp))

    def test_no_checkout_means_no_updates(self):
        lib = self.tmp / "share" / "inkwell"
        (lib / "inkwell").mkdir(parents=True)
        self.assertIsNone(updater.find_install(lib / "inkwell"))
        (lib / "install-info").write_text(f"source={self.tmp / 'gone'}\n")
        self.assertIsNone(updater.find_install(lib / "inkwell"))
        self.assertEqual(Updater(None).state, Updater.UNAVAILABLE)

    def test_errors_are_readable(self):
        message = updater.describe_error(
            "fatal: could not read Username for 'https://github.com'", "/src"
        )
        self.assertIn("sign-in", message)
        self.assertEqual(updater.describe_error("one\ntwo\n\n", "/src"), "two")


class CheckAndUpdateTests(unittest.TestCase):
    """Drive the updater against a real local git remote."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.remote = self.tmp / "remote.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.remote))
        upstream = self.tmp / "upstream"
        git(self.tmp, "clone", "-q", str(self.remote), str(upstream))
        git(upstream, "checkout", "-q", "-b", "main")
        # A stand-in update.sh that only pulls (the real one also installs).
        (upstream / "update.sh").write_text("#!/bin/sh\nset -e\ngit pull -q --ff-only origin main\n")
        git(upstream, "add", "update.sh")
        git(upstream, "commit", "-q", "-m", "First")
        git(upstream, "push", "-q", "origin", "main")
        self.upstream = upstream
        self.checkout = self.tmp / "checkout"
        git(self.tmp, "clone", "-q", str(self.remote), str(self.checkout))

    def wait(self, upd):
        loop = GLib.MainLoop()

        def on_change(u):
            if not u.busy:
                loop.quit()

        upd.connect(on_change)
        GLib.timeout_add_seconds(20, loop.quit)
        loop.run()
        upd.disconnect(on_change)

    def test_up_to_date(self):
        upd = Updater(updater.Install(source=self.checkout))
        upd.check()
        self.wait(upd)
        self.assertEqual(upd.state, Updater.UP_TO_DATE, upd.message)

    def test_finds_and_installs_new_commits(self):
        commit(self.upstream, "a.txt", "Add a")
        commit(self.upstream, "b.txt", "Add b")
        git(self.upstream, "push", "-q", "origin", "main")

        upd = Updater(updater.Install(source=self.checkout))
        upd.check()
        self.wait(upd)
        self.assertEqual(upd.state, Updater.AVAILABLE, upd.message)
        self.assertEqual(upd.new_commits, ["Add b", "Add a"])

        upd.update()
        self.wait(upd)
        self.assertEqual(upd.state, Updater.UPDATED, upd.message)
        self.assertTrue((self.checkout / "b.txt").exists())

    def test_installed_commit_is_compared_not_the_checkout(self):
        installed = git(self.checkout, "rev-parse", "HEAD")
        commit(self.upstream, "a.txt", "Add a")
        git(self.upstream, "push", "-q", "origin", "main")
        git(self.checkout, "pull", "-q", "origin", "main")
        # The checkout was pulled but never reinstalled: still an update.
        upd = Updater(updater.Install(source=self.checkout, commit=installed))
        upd.check()
        self.wait(upd)
        self.assertEqual(upd.new_commits, ["Add a"])


if __name__ == "__main__":
    unittest.main()
