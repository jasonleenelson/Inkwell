"""Application entry point."""

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Adw, Gdk, Gio, GObject, Gtk, GtkSource  # noqa: E402

from . import APP_ID, __version__, appearance, updater  # noqa: E402
from .config import Config  # noqa: E402
from .preferences import PreferencesDialog  # noqa: E402
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
  background: none;
  padding: 0 18px;
}
.attachments scrolledwindow > viewport > box {
  padding: 8px 18px 10px 18px;
}
.attachment {
  padding: 4px;
}
.attachment-preview {
  border-radius: 8px;
}
"""


# GTK's default text resolution, in 1/1024ths of a dot per inch.
DEFAULT_DPI = 96 * 1024

# GTK 4.16 added automatic font rendering, which ignores the hinting settings.
HAS_FONT_RENDERING = hasattr(Gtk, "FontRendering")

# The Gtk.Settings that "Sharp Text" overrides.
SHARP_TEXT_SETTINGS = ("gtk-hint-font-metrics", "gtk-xft-hinting", "gtk-xft-hintstyle") + (
    ("gtk-font-rendering",) if HAS_FONT_RENDERING else ()
)


class InkwellApplication(Adw.Application):
    zoom = GObject.Property(type=int, default=appearance.DEFAULT_ZOOM)
    editor_font_size = GObject.Property(type=int, default=appearance.DEFAULT_FONT_SIZE)
    sharp_text = GObject.Property(type=bool, default=True)

    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.config = Config()
        self.zoom = appearance.clamp_zoom(self.config.get("zoom", appearance.DEFAULT_ZOOM))
        self.editor_font_size = appearance.clamp_font_size(
            self.config.get("editor_font_size", appearance.DEFAULT_FONT_SIZE)
        )
        self.sharp_text = bool(self.config.get("sharp_text", True))
        self.updater = updater.Updater(updater.find_install())
        self.restart_requested = False

    def do_startup(self):
        Adw.Application.do_startup(self)
        Gtk.Window.set_default_icon_name(APP_ID)
        GtkSource.init()

        # The list icons are bundled because icon themes name them
        # inconsistently (Breeze has no view-list-ordered-symbolic, for one).
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(
            os.path.join(os.path.dirname(__file__), "icons")
        )

        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Zoom works by scaling GTK's text resolution, which every font size
        # in the app (the editor's included) is measured against.
        self.font_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.font_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
        )
        self.gtk_settings = Gtk.Settings.get_default()
        self._system_dpi = self.gtk_settings.props.gtk_xft_dpi
        if self._system_dpi <= 0:
            self._system_dpi = DEFAULT_DPI
        self._applied_dpi = None
        self.gtk_settings.connect("notify::gtk-xft-dpi", self._on_system_dpi_changed)
        self._apply_zoom()
        self._apply_font_size()
        self._apply_sharp_text()

        for name, handler in (
            ("quit", self._on_quit),
            ("about", self._on_about),
            ("preferences", self._on_preferences),
            ("zoom-in", lambda *_: self.set_zoom(appearance.zoom_in(self.zoom))),
            ("zoom-out", lambda *_: self.set_zoom(appearance.zoom_out(self.zoom))),
            ("zoom-reset", lambda *_: self.set_zoom(appearance.DEFAULT_ZOOM)),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

        for action, keys in (
            ("app.quit", ["<Control>q"]),
            ("app.preferences", ["<Control>comma"]),
            ("app.zoom-in", ["<Control>plus", "<Control>equal", "<Control>KP_Add"]),
            ("app.zoom-out", ["<Control>minus", "<Control>KP_Subtract"]),
            ("app.zoom-reset", ["<Control>0", "<Control>KP_0"]),
            ("win.new-note('')", ["<Control>n"]),
            ("win.new-folder('')", ["<Control><Shift>n"]),
            ("win.save", ["<Control>s"]),
            ("win.find", ["<Control>f"]),
            ("win.bold", ["<Control>b"]),
            ("win.italic", ["<Control>i"]),
            ("win.heading", ["<Control>h"]),
            ("win.link", ["<Control>k"]),
            ("win.attach", ["<Control><Shift>a"]),
        ):
            self.set_accels_for_action(action, keys)

    def do_activate(self):
        window = self.get_active_window() or InkwellWindow(self, self.config)
        window.present()

    # Text size and zoom ---------------------------------------------------

    def set_zoom(self, percent):
        percent = appearance.clamp_zoom(percent)
        if percent == self.zoom:
            return
        self.zoom = percent
        self._apply_zoom()
        self.config.set("zoom", percent)
        self.config.save()

    def set_editor_font_size(self, points):
        points = appearance.clamp_font_size(points)
        if points == self.editor_font_size:
            return
        self.editor_font_size = points
        self._apply_font_size()
        self.config.set("editor_font_size", points)
        self.config.save()

    def set_sharp_text(self, sharp):
        sharp = bool(sharp)
        if sharp == self.sharp_text:
            return
        self.sharp_text = sharp
        self._apply_sharp_text()
        self.config.set("sharp_text", sharp)
        self.config.save()

    def _apply_sharp_text(self):
        # Without hinting, letter heights don't line up with the pixel grid on
        # an ordinary (non-HiDPI) screen, so the top edge of a capital E or F
        # lands part way through a pixel row and is drawn faint, as if cut
        # off. Sharp text turns on (at least slight) hinting for letters and
        # line positions; GTK 4.16+ only honours that in its "manual" mode.
        settings = self.gtk_settings
        if not self.sharp_text:
            # Hand these back to the desktop.
            for name in SHARP_TEXT_SETTINGS:
                settings.reset_property(name)
            return
        if HAS_FONT_RENDERING:
            settings.props.gtk_font_rendering = Gtk.FontRendering.MANUAL
        settings.props.gtk_hint_font_metrics = True
        settings.props.gtk_xft_hinting = 1
        # Keep stronger hinting if the desktop asks for it.
        if settings.props.gtk_xft_hintstyle not in ("hintmedium", "hintfull"):
            settings.props.gtk_xft_hintstyle = "hintslight"

    def _apply_zoom(self):
        self._applied_dpi = round(self._system_dpi * self.zoom / 100)
        self.gtk_settings.props.gtk_xft_dpi = self._applied_dpi

    def _apply_font_size(self):
        self.font_provider.load_from_string(
            f".note-body {{ font-size: {self.editor_font_size}pt; }}"
        )

    def _on_system_dpi_changed(self, settings, _pspec):
        # The desktop's own text scaling changed: zoom relative to the new value.
        dpi = settings.props.gtk_xft_dpi
        if dpi == self._applied_dpi:
            return
        self._system_dpi = dpi if dpi > 0 else DEFAULT_DPI
        self._apply_zoom()

    def _on_preferences(self, *_args):
        PreferencesDialog(self).present(self.get_active_window())

    def restart(self):
        """Close every window (which saves the open note) and start again."""
        self.restart_requested = True
        self._on_quit()

    def _on_quit(self, *_args):
        for window in self.get_windows():
            # A window won't close while it shows a dialog such as Preferences.
            dialog = window.get_visible_dialog() if hasattr(window, "get_visible_dialog") else None
            if dialog:
                dialog.force_close()
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
    app = InkwellApplication()
    status = app.run(sys.argv)
    if app.restart_requested:
        command = updater.restart_command(sys.argv)
        os.execv(command[0], command)
    return status
