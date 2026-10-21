"""The Preferences dialog."""

from gi.repository import Adw, Gtk

from . import appearance


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

        reset = Gtk.Button(label="Reset", valign=Gtk.Align.CENTER)
        reset.add_css_class("flat")
        reset.connect("clicked", self._on_reset)
        group.set_header_suffix(reset)

        page = Adw.PreferencesPage()
        page.add(group)
        self.add(page)

        # Keep the rows in step when the shortcuts change things meanwhile.
        self._handlers = [
            app.connect("notify::zoom", self._on_app_zoom),
            app.connect("notify::editor-font-size", self._on_app_font_size),
        ]
        self.connect("closed", self._on_closed)

    def _on_font_size_changed(self, row, _pspec):
        self.app.set_editor_font_size(row.get_value())

    def _on_zoom_changed(self, row, _pspec):
        self.app.set_zoom(appearance.ZOOM_LEVELS[row.get_selected()])

    def _on_reset(self, _button):
        self.app.set_editor_font_size(appearance.DEFAULT_FONT_SIZE)
        self.app.set_zoom(appearance.DEFAULT_ZOOM)

    def _on_app_zoom(self, app, _pspec):
        index = appearance.ZOOM_LEVELS.index(app.zoom)
        if self.zoom_row.get_selected() != index:
            self.zoom_row.set_selected(index)

    def _on_app_font_size(self, app, _pspec):
        if self.font_size_row.get_value() != app.editor_font_size:
            self.font_size_row.set_value(app.editor_font_size)

    def _on_closed(self, _dialog):
        for handler in self._handlers:
            self.app.disconnect(handler)
        self._handlers = []
