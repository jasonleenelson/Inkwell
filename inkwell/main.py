"""Application entry point."""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gi.repository import Adw, Gdk, Gio, Gtk, GtkSource  # noqa: E402

from . import APP_ID, __version__  # noqa: E402
from .config import Config  # noqa: E402
from .window import InkwellWindow  # noqa: E402

CSS = """
.note-title {
  font-size: 1.8em;
  font-weight: 800;
  background: none;
  box-shadow: none;
  outline: none;
  margin: 24px 12px 0 12px;
  padding: 0 6px;
  min-height: 48px;
}
.note-body {
  font-size: 1.05em;
  background: none;
  padding: 0 18px;
}
"""


class InkwellApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.config = Config()

    def do_startup(self):
        Adw.Application.do_startup(self)
        Gtk.Window.set_default_icon_name(APP_ID)
        GtkSource.init()

        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        for name, handler in (("quit", self._on_quit), ("about", self._on_about)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

        for action, keys in (
            ("app.quit", ["<Control>q"]),
            ("win.new-note('')", ["<Control>n"]),
            ("win.new-folder('')", ["<Control><Shift>n"]),
            ("win.save", ["<Control>s"]),
            ("win.find", ["<Control>f"]),
            ("win.bold", ["<Control>b"]),
            ("win.italic", ["<Control>i"]),
            ("win.heading", ["<Control>h"]),
            ("win.link", ["<Control>k"]),
        ):
            self.set_accels_for_action(action, keys)

    def do_activate(self):
        window = self.get_active_window() or InkwellWindow(self, self.config)
        window.present()

    def _on_quit(self, *_args):
        for window in self.get_windows():
            window.close()

    def _on_about(self, *_args):
        about = Adw.AboutDialog(
            application_name="Inkwell",
            application_icon=APP_ID,
            version=__version__,
            comments="Simple Markdown notes, kept as plain files in folders.",
            website="https://github.com/jasonleenelson/Simple-Markdown-Notetaking-App",
            license_type=Gtk.License.MIT_X11,
            developers=["Jason"],
        )
        about.present(self.get_active_window())


def main():
    return InkwellApplication().run(sys.argv)
