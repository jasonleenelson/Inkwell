"""The Preferences dialog."""

from gi.repository import Adw, GLib, Gtk

from . import appearance
from .updater import Updater


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, app):
        super().__init__(title="Preferences")
        self.app = app

        group = Adw.PreferencesGroup(
            title="Text",
            description="Zoom scales all text in Inkwell. Ctrl+Plus, Ctrl+Minus and Ctrl+0 "
            "change it from anywhere.",
        )

        self.font_size_row = Adw.SpinRow.new_with_range(
            appearance.MIN_FONT_SIZE, appearance.MAX_FONT_SIZE, 1
        )
        self.font_size_row.set_title("Editor Text Size")
        self.font_size_row.set_subtitle("In points")
        self.font_size_row.set_value(app.editor_font_size)
        self.font_size_row.connect("notify::value", self._on_font_size_changed)
        group.add(self.font_size_row)

        labels = [f"{level}%" for level in appearance.ZOOM_LEVELS]
        self.zoom_row = Adw.ComboRow(title="Zoom", model=Gtk.StringList.new(labels))
        self.zoom_row.set_selected(appearance.ZOOM_LEVELS.index(app.zoom))
        self.zoom_row.connect("notify::selected", self._on_zoom_changed)
        group.add(self.zoom_row)

        self.sharp_row = Adw.SwitchRow(
            title="Sharp Text",
            subtitle="Line text up with screen pixels so letters are not blurred or cut "
            "off at the top. Turn off to use your desktop's own font rendering.",
            active=app.sharp_text,
        )
        self.sharp_row.connect("notify::active", self._on_sharp_changed)
        group.add(self.sharp_row)

        reset = Gtk.Button(label="Reset", valign=Gtk.Align.CENTER)
        reset.add_css_class("flat")
        reset.connect("clicked", self._on_reset)
        group.set_header_suffix(reset)

        page = Adw.PreferencesPage()
        page.add(group)
        page.add(self._build_updates_group())
        self.add(page)

        # Keep the rows in step when the shortcuts change things meanwhile.
        self._handlers = [
            app.connect("notify::zoom", self._on_app_zoom),
            app.connect("notify::editor-font-size", self._on_app_font_size),
            app.connect("notify::sharp-text", self._on_app_sharp_text),
        ]
        app.updater.connect(self._show_update_state)
        self.connect("closed", self._on_closed)

    def _build_updates_group(self):
        group = Adw.PreferencesGroup(title="Updates")
        self.update_row = Adw.ActionRow(title="Check for Updates")
        self.update_row.set_subtitle_selectable(True)

        self.update_button = Gtk.Button(valign=Gtk.Align.CENTER)
        self.update_button.connect("clicked", self._on_update_clicked)
        spinner_class = getattr(Adw, "Spinner", None)
        if spinner_class:
            self.update_spinner = spinner_class()
        else:
            self.update_spinner = Gtk.Spinner(spinning=True)
        self.update_spinner.set_valign(Gtk.Align.CENTER)
        self.update_suffix = Gtk.Stack()
        self.update_suffix.add_named(self.update_button, "button")
        self.update_suffix.add_named(self.update_spinner, "spinner")
        self.update_row.add_suffix(self.update_suffix)

        group.add(self.update_row)
        self._show_update_state(self.app.updater)
        return group

    def _show_update_state(self, updater):
        state = updater.state
        busy = updater.busy
        self.update_suffix.set_visible_child_name("spinner" if busy else "button")
        self.update_button.remove_css_class("suggested-action")
        self.update_button.set_sensitive(state != Updater.UNAVAILABLE)
        label, subtitle = "Check", "Get the newest Inkwell from GitHub. Your notes are not touched."
        if state == Updater.UNAVAILABLE:
            subtitle = (
                "Updates work when Inkwell was installed with “make install” "
                "from a git checkout."
            )
        elif state == Updater.CHECKING:
            subtitle = "Checking GitHub…"
        elif state == Updater.UP_TO_DATE:
            subtitle = "Inkwell is up to date."
        elif state == Updater.AVAILABLE:
            label = "Update"
            self.update_button.add_css_class("suggested-action")
            count = len(updater.new_commits)
            changes = [f"• {GLib.markup_escape_text(c)}" for c in updater.new_commits[:3]]
            if count > 3:
                changes.append(f"…and {count - 3} more")
            heading = "1 update is ready." if count == 1 else f"{count} updates are ready."
            subtitle = "\n".join([heading, *changes])
        elif state == Updater.UPDATING:
            subtitle = "Updating… This takes a few seconds."
        elif state == Updater.UPDATED:
            label = "Restart"
            self.update_button.add_css_class("suggested-action")
            subtitle = "Updated. Restart Inkwell to use the new version."
        elif state == Updater.FAILED:
            label = "Try Again"
            subtitle = GLib.markup_escape_text(updater.message)
        self.update_button.set_label(label)
        self.update_row.set_subtitle(subtitle)

    def _on_update_clicked(self, _button):
        updater = self.app.updater
        if updater.state == Updater.AVAILABLE:
            updater.update()
        elif updater.state == Updater.UPDATED:
            self.app.restart()
        else:
            updater.check()

    def _on_font_size_changed(self, row, _pspec):
        self.app.set_editor_font_size(row.get_value())

    def _on_zoom_changed(self, row, _pspec):
        self.app.set_zoom(appearance.ZOOM_LEVELS[row.get_selected()])

    def _on_sharp_changed(self, row, _pspec):
        self.app.set_sharp_text(row.get_active())

    def _on_reset(self, _button):
        self.app.set_editor_font_size(appearance.DEFAULT_FONT_SIZE)
        self.app.set_zoom(appearance.DEFAULT_ZOOM)
        self.app.set_sharp_text(True)

    def _on_app_zoom(self, app, _pspec):
        index = appearance.ZOOM_LEVELS.index(app.zoom)
        if self.zoom_row.get_selected() != index:
            self.zoom_row.set_selected(index)

    def _on_app_font_size(self, app, _pspec):
        if self.font_size_row.get_value() != app.editor_font_size:
            self.font_size_row.set_value(app.editor_font_size)

    def _on_app_sharp_text(self, app, _pspec):
        if self.sharp_row.get_active() != app.sharp_text:
            self.sharp_row.set_active(app.sharp_text)

    def _on_closed(self, _dialog):
        for handler in self._handlers:
            self.app.disconnect(handler)
        self._handlers = []
        self.app.updater.disconnect(self._show_update_state)
