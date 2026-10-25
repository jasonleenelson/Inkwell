"""The note editor: a title field and a Markdown text view."""

import re
from pathlib import Path

from gi.repository import Adw, Gdk, GLib, GObject, Gtk, GtkSource

from . import store

AUTOSAVE_DELAY_MS = 800

# "- ", "* ", "+ ", "1. " and task boxes, with any leading indentation.
LIST_ITEM = re.compile(r"^(\s*)([-*+]|(\d+)[.)])(\s+)(\[[ xX]\]\s+)?")
HEADING = re.compile(r"^(#{1,6})\s+")


class NoteEditor(Gtk.Box):
    __gsignals__ = {
        # (old path, new path) after the title field renamed the file.
        "renamed": (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        "error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.path = None
        self._loading = False
        self._dirty = False
        self._save_source = 0

        self.title_entry = Gtk.Entry(placeholder_text="Untitled")
        self.title_entry.add_css_class("note-title")
        self.title_entry.connect("activate", self._on_title_activate)
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: self.commit_title())
        self.title_entry.add_controller(focus)

        self.buffer = GtkSource.Buffer()
        language = GtkSource.LanguageManager.get_default().get_language("markdown")
        if language:
            self.buffer.set_language(language)
        self.buffer.set_highlight_matching_brackets(False)
        self.buffer.connect("changed", self._on_changed)

        # vexpand lets clicks below a short note still land in the text.
        self.view = GtkSource.View(buffer=self.buffer, vexpand=True)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_auto_indent(True)
        self.view.set_tab_width(4)
        self.view.set_insert_spaces_instead_of_tabs(True)
        self.view.set_top_margin(12)
        self.view.set_bottom_margin(48)
        self.view.add_css_class("note-body")
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key_pressed)
        self.view.add_controller(keys)

        self.search_settings = GtkSource.SearchSettings(wrap_around=True)
        self.search_context = GtkSource.SearchContext.new(self.buffer, self.search_settings)
        self.search_entry = Gtk.SearchEntry(hexpand=True, placeholder_text="Find in note")
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("activate", lambda *_: self.find_next())
        self.search_entry.connect("next-match", lambda *_: self.find_next())
        self.search_entry.connect("previous-match", lambda *_: self.find_previous())
        self.search_entry.connect("stop-search", lambda *_: self.search_bar.set_search_mode(False))
        self.search_bar = Gtk.SearchBar(child=Adw.Clamp(child=self.search_entry, maximum_size=500))
        self.search_bar.connect_entry(self.search_entry)
        self.append(self.search_bar)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        column.append(self.title_entry)
        column.append(self.view)
        clamp = Adw.Clamp(child=column, maximum_size=760, tightening_threshold=600)
        scroller = Gtk.ScrolledWindow(vexpand=True, child=clamp)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroller)

        style = Adw.StyleManager.get_default()
        style.connect("notify::dark", lambda *_: self._update_scheme())
        self._update_scheme()

    # Opening and saving --------------------------------------------------

    def open(self, path):
        """Show the note at ``path``. Raises ``store.NoteError`` if unreadable."""
        path = Path(path)
        text = store.read_note(path)
        self.save_now()
        self.path = path
        self._loading = True
        self.buffer.begin_irreversible_action()
        self.buffer.set_text(text)
        self.buffer.end_irreversible_action()
        self._loading = False
        self._dirty = False
        self.buffer.place_cursor(self.buffer.get_start_iter())
        self.title_entry.set_text(store.note_title(path))

    def close(self, save=True):
        if save:
            self.save_now()
        else:
            self._cancel_autosave()
            self._dirty = False
        self.path = None
        self._loading = True
        self.buffer.set_text("")
        self._loading = False
        self.title_entry.set_text("")

    def text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), True)

    def save_now(self):
        self._cancel_autosave()
        if not (self.path and self._dirty):
            return True
        try:
            store.write_note(self.path, self.text())
        except OSError as error:
            self.emit("error", f"Couldn't save “{store.note_title(self.path)}”: {error.strerror}")
            return False
        self._dirty = False
        return True

    def relocate(self, old, new):
        """Follow the open note after it, or a folder above it, moved."""
        if self.path is None:
            return
        old, new = Path(old), Path(new)
        if self.path == old:
            self.path = new
        elif old in self.path.parents:
            self.path = new / self.path.relative_to(old)
        else:
            return
        self.title_entry.set_text(store.note_title(self.path))

    def _on_changed(self, _buffer):
        if self._loading or self.path is None:
            return
        self._dirty = True
        self._cancel_autosave()
        self._save_source = GLib.timeout_add(AUTOSAVE_DELAY_MS, self._autosave)

    def _autosave(self):
        self._save_source = 0
        self.save_now()
        return GLib.SOURCE_REMOVE

    def _cancel_autosave(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
            self._save_source = 0

    # Title ---------------------------------------------------------------

    def _on_title_activate(self, _entry):
        self.commit_title()
        self.view.grab_focus()

    def commit_title(self):
        if self.path is None:
            return
        name = self.title_entry.get_text().strip()
        if not name or name == store.note_title(self.path):
            self.title_entry.set_text(store.note_title(self.path))
            return
        self.save_now()
        old = self.path
        try:
            new = store.rename(old, name)
        except (store.NoteError, OSError) as error:
            self.title_entry.set_text(store.note_title(old))
            self.emit("error", str(error) if isinstance(error, store.NoteError) else error.strerror)
            return
        self.path = new
        self.title_entry.set_text(store.note_title(new))
        self.emit("renamed", old, new)

    def focus_title(self):
        self.title_entry.grab_focus()
        self.title_entry.select_region(0, -1)

    def focus_text(self, offset=None):
        """Focus the text, optionally putting the cursor ``offset`` characters in."""
        if offset is not None:
            self.buffer.place_cursor(self.buffer.get_iter_at_offset(offset))
        self.view.grab_focus()

    # Formatting ----------------------------------------------------------

    def wrap_selection(self, marker):
        """Surround the selection with ``marker``, or remove it if present."""
        buf = self.buffer
        buf.begin_user_action()
        if buf.get_has_selection():
            start, end = buf.get_selection_bounds()
            offset = start.get_offset()
            text = buf.get_text(start, end, True)
            size = len(marker)
            if len(text) >= 2 * size and text.startswith(marker) and text.endswith(marker):
                text = text[size:-size]
            else:
                text = f"{marker}{text}{marker}"
            buf.delete(start, end)
            buf.insert(buf.get_iter_at_offset(offset), text)
            buf.select_range(
                buf.get_iter_at_offset(offset), buf.get_iter_at_offset(offset + len(text))
            )
        else:
            cursor = buf.get_iter_at_mark(buf.get_insert())
            offset = cursor.get_offset()
            buf.insert(cursor, marker * 2)
            buf.place_cursor(buf.get_iter_at_offset(offset + len(marker)))
        buf.end_user_action()
        self.view.grab_focus()

    def toggle_line_prefix(self, prefix):
        """Add ``prefix`` to every selected line, or remove it from all of them."""
        buf = self.buffer
        lines = self._selected_lines()
        texts = [self._line_text(line) for line in lines]
        remove = all(text.startswith(prefix) for text in texts)
        buf.begin_user_action()
        for number, line in enumerate(lines, start=1):
            start = self._line_start(line)
            if remove:
                end = start.copy()
                end.forward_chars(len(prefix))
                buf.delete(start, end)
            elif prefix == "1. ":
                buf.insert(start, f"{number}. ")
            else:
                buf.insert(start, prefix)
        buf.end_user_action()
        self.view.grab_focus()

    def cycle_heading(self):
        """Turn the current line into a heading: none → # → ## → ### → none."""
        buf = self.buffer
        line = buf.get_iter_at_mark(buf.get_insert()).get_line()
        text = self._line_text(line)
        match = HEADING.match(text)
        level = len(match.group(1)) if match else 0
        buf.begin_user_action()
        start = self._line_start(line)
        if match:
            end = start.copy()
            end.forward_chars(match.end())
            buf.delete(start, end)
            start = self._line_start(line)
        if level < 3:
            buf.insert(start, "#" * (level + 1) + " ")
        buf.end_user_action()
        self.view.grab_focus()

    def insert_link(self):
        buf = self.buffer
        buf.begin_user_action()
        if buf.get_has_selection():
            start, end = buf.get_selection_bounds()
            offset = start.get_offset()
            label = buf.get_text(start, end, True)
            buf.delete(start, end)
        else:
            offset = buf.get_iter_at_mark(buf.get_insert()).get_offset()
            label = "link text"
        text = f"[{label}](https://)"
        buf.insert(buf.get_iter_at_offset(offset), text)
        url_start = offset + len(label) + 3
        buf.select_range(
            buf.get_iter_at_offset(url_start), buf.get_iter_at_offset(url_start + len("https://"))
        )
        buf.end_user_action()
        self.view.grab_focus()

    def _selected_lines(self):
        buf = self.buffer
        if buf.get_has_selection():
            start, end = buf.get_selection_bounds()
        else:
            start = end = buf.get_iter_at_mark(buf.get_insert())
        first, last = start.get_line(), end.get_line()
        if last > first and end.starts_line():
            last -= 1
        return list(range(first, last + 1))

    def _line_start(self, line):
        result = self.buffer.get_iter_at_line(line)
        # GTK 4 returns (found, iter); keep working if that ever changes.
        return result[1] if isinstance(result, tuple) else result

    def _line_text(self, line):
        start = self._line_start(line)
        end = start.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        return self.buffer.get_text(start, end, True)

    def _on_key_pressed(self, _controller, keyval, _keycode, state):
        if keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        if state & (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK):
            return False
        if self.buffer.get_has_selection():
            return False
        return self._continue_list()

    def _continue_list(self):
        """Pressing Enter in a list starts the next item, or ends an empty list."""
        buf = self.buffer
        cursor = buf.get_iter_at_mark(buf.get_insert())
        line = cursor.get_line()
        text = self._line_text(line)
        match = LIST_ITEM.match(text)
        if not match:
            return False
        buf.begin_user_action()
        if match.end() >= len(text.rstrip()) and cursor.ends_line():
            # An empty item: remove the bullet instead of adding another.
            start = self._line_start(line)
            end = start.copy()
            end.forward_to_line_end()
            buf.delete(start, end)
        else:
            indent, bullet, number, space, task = match.groups()
            if number is not None:
                bullet = f"{int(number) + 1}{bullet[-1]}"
            prefix = f"{indent}{bullet}{space}{'[ ] ' if task else ''}"
            buf.insert_at_cursor("\n" + prefix)
        buf.end_user_action()
        self.view.scroll_mark_onscreen(buf.get_insert())
        return True

    # Find ----------------------------------------------------------------

    def show_find(self):
        self.search_bar.set_search_mode(True)
        if self.buffer.get_has_selection():
            start, end = self.buffer.get_selection_bounds()
            self.search_entry.set_text(self.buffer.get_text(start, end, True))
        self.search_entry.grab_focus()

    def _on_search_changed(self, entry):
        self.search_settings.set_search_text(entry.get_text() or None)
        self.find_next(from_selection_start=True)

    def find_next(self, from_selection_start=False):
        buf = self.buffer
        if buf.get_has_selection():
            start, end = buf.get_selection_bounds()
            origin = start if from_selection_start else end
        else:
            origin = buf.get_iter_at_mark(buf.get_insert())
        found, start, end, _wrapped = self.search_context.forward(origin)
        if found:
            buf.select_range(start, end)
            self.view.scroll_to_iter(start, 0.2, False, 0, 0)

    def find_previous(self):
        buf = self.buffer
        origin = buf.get_iter_at_mark(buf.get_insert())
        found, start, end, _wrapped = self.search_context.backward(origin)
        if found:
            buf.select_range(start, end)
            self.view.scroll_to_iter(start, 0.2, False, 0, 0)

    # Misc ----------------------------------------------------------------

    def _update_scheme(self):
        dark = Adw.StyleManager.get_default().get_dark()
        manager = GtkSource.StyleSchemeManager.get_default()
        scheme = manager.get_scheme("Adwaita-dark" if dark else "Adwaita")
        if scheme:
            self.buffer.set_style_scheme(scheme)
