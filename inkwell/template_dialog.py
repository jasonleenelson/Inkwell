"""The dialog for setting up a folder's note template."""

from datetime import datetime
from pathlib import Path

from gi.repository import Adw, Gio, GLib, GObject, Gtk, GtkSource, Pango

from . import templates


class TemplateDialog(Adw.Dialog):
    __gsignals__ = {
        "error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, folder, root):
        super().__init__(content_width=560, content_height=620)
        self.folder = Path(folder)
        name = "your notes folder" if self.folder == Path(root) else f"“{self.folder.name}”"
        self.set_title("Note Template")
        existing = templates.load(self.folder)
        template = existing or templates.Template()

        self.title_row = Adw.EntryRow(title="Title for new notes", text=template.title)
        self.title_row.connect("changed", lambda *_: self._update_preview())
        title_group = Adw.PreferencesGroup(
            description=f"New notes in {name} start like this. "
            "Leave the title empty to call them “Untitled”."
        )
        title_group.add(self.title_row)
        self.preview = Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        self.preview.add_css_class("dim-label")
        self.preview.add_css_class("caption")
        self.preview.set_margin_top(6)
        self.preview.set_margin_start(12)
        title_group.add(self.preview)

        self.buffer = GtkSource.Buffer(text=template.body)
        language = GtkSource.LanguageManager.get_default().get_language("markdown")
        if language:
            self.buffer.set_language(language)
        style = Adw.StyleManager.get_default()
        scheme = GtkSource.StyleSchemeManager.get_default().get_scheme(
            "Adwaita-dark" if style.get_dark() else "Adwaita"
        )
        if scheme:
            self.buffer.set_style_scheme(scheme)
        view = GtkSource.View(buffer=self.buffer, monospace=False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_auto_indent(True)
        for side in ("top", "bottom", "left", "right"):
            getattr(view, f"set_{side}_margin")(10)
        frame = Gtk.ScrolledWindow(child=view, vexpand=True, min_content_height=200)
        frame.add_css_class("card")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        body_group = Adw.PreferencesGroup(title="Note Text")
        body_group.add(frame)

        help_group = Adw.PreferencesGroup(
            title="Placeholders", description="Filled in when a note is made."
        )
        for code, meaning in templates.PLACEHOLDERS:
            row = Adw.ActionRow(title=GLib.markup_escape_text(code), subtitle=meaning)
            row.add_css_class("property")
            help_group.add(row)

        page = Adw.PreferencesPage()
        page.add(title_group)
        page.add(body_group)
        page.add(help_group)

        if existing is not None:
            remove = Gtk.Button(label="Remove Template", halign=Gtk.Align.CENTER)
            remove.add_css_class("destructive-action")
            remove.add_css_class("pill")
            remove.connect("clicked", self._on_remove)
            remove_group = Adw.PreferencesGroup()
            remove_group.add(remove)
            page.add(remove_group)

        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        save = Gtk.Button(label="Save")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._on_save)
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        header.pack_start(cancel)
        header.pack_end(save)

        toolbar = Adw.ToolbarView(content=page)
        toolbar.add_top_bar(header)
        self.set_child(toolbar)
        self.set_default_widget(save)
        self._update_preview()

    def _template(self):
        start, end = self.buffer.get_bounds()
        return templates.Template(self.title_row.get_text(), self.buffer.get_text(start, end, True))

    def _update_preview(self):
        title = templates.note_title(self._template(), self.folder, datetime.now())
        self.preview.set_label(f"A note made now would be called “{title}”.")

    def _on_save(self, _button):
        try:
            templates.save(self.folder, self._template())
        except OSError as error:
            self.emit("error", f"Couldn't save the template: {error.strerror}")
            return
        self.close()

    def _on_remove(self, _button):
        # To the Trash rather than deleted, in case it was removed by mistake.
        try:
            Gio.File.new_for_path(str(templates.template_path(self.folder))).trash(None)
        except GLib.Error as error:
            self.emit("error", f"Couldn't remove the template: {error.message}")
            return
        self.close()

