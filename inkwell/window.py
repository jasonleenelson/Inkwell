"""The main window: sidebar on the left, editor on the right."""

from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from . import store
from .editor import NoteEditor
from .sidebar import Sidebar

FORMAT_ACTIONS = {
    "bold": ("wrap_selection", "**"),
    "italic": ("wrap_selection", "*"),
    "strikethrough": ("wrap_selection", "~~"),
    "code": ("wrap_selection", "`"),
    "heading": ("cycle_heading",),
    "bullet-list": ("toggle_line_prefix", "- "),
    "numbered-list": ("toggle_line_prefix", "1. "),
    "task-list": ("toggle_line_prefix", "- [ ] "),
    "quote": ("toggle_line_prefix", "> "),
    "link": ("insert_link",),
}


class InkwellWindow(Adw.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app, title="Inkwell")
        self.config = config
        self.set_default_size(config.get("width", 1000), config.get("height", 680))
        if config.get("maximized"):
            self.maximize()

        self.sidebar = Sidebar()
        self.sidebar.connect("note-selected", self._on_note_selected)
        self.sidebar.connect("move-requested", self._on_move_requested)

        self.editor = NoteEditor()
        self.editor.connect("renamed", self._on_editor_renamed)
        self.editor.connect("error", lambda _e, message: self.toast(message))

        self.split = Adw.NavigationSplitView(
            sidebar=self._build_sidebar_page(), content=self._build_content_page()
        )
        self.set_content(self.split)
        self.set_size_request(360, 300)

        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 640sp"))
        breakpoint.add_setter(self.split, "collapsed", True)
        breakpoint.add_setter(self.formatting, "visible", False)
        self.add_breakpoint(breakpoint)

        self._install_actions()
        self.connect("close-request", self._on_close_request)

        self.load_notes_dir(config.notes_dir)
        last = config.get("last_note")
        if last:
            path = self.notes_dir / last
            if path.is_file():
                self.open_note(path)

    # Layout --------------------------------------------------------------

    def _build_sidebar_page(self):
        header = Adw.HeaderBar()
        new_note = Gtk.Button(icon_name="document-new-symbolic", tooltip_text="New Note (Ctrl+N)")
        new_note.set_detailed_action_name("win.new-note('')")
        new_folder = Gtk.Button(
            icon_name="folder-new-symbolic", tooltip_text="New Folder (Ctrl+Shift+N)"
        )
        new_folder.set_detailed_action_name("win.new-folder('')")
        header.pack_start(new_note)
        header.pack_start(new_folder)

        menu = Gio.Menu()
        section = Gio.Menu()
        section.append("Change Notes Folder…", "win.change-folder")
        section.append("Open Notes Folder in Files", "win.open-folder")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append("Preferences", "app.preferences")
        section.append("Keyboard Shortcuts", "win.shortcuts")
        section.append("About Inkwell", "app.about")
        menu.append_section(None, section)
        header.pack_end(
            Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menu")
        )

        view = Adw.ToolbarView(content=self.sidebar)
        view.add_top_bar(header)
        return Adw.NavigationPage(title="Notes", child=view)

    def _build_content_page(self):
        header = Adw.HeaderBar()
        self.window_title = Adw.WindowTitle()
        header.set_title_widget(self.window_title)

        formatting = Gtk.Box(spacing=2)
        for icon, label, action, tip in (
            ("format-text-bold-symbolic", None, "bold", "Bold (Ctrl+B)"),
            ("format-text-italic-symbolic", None, "italic", "Italic (Ctrl+I)"),
            ("format-text-strikethrough-symbolic", None, "strikethrough", "Strikethrough"),
            (None, "H", "heading", "Heading (Ctrl+H)"),
            ("view-list-bullet-symbolic", None, "bullet-list", "Bulleted List"),
            ("view-list-ordered-symbolic", None, "numbered-list", "Numbered List"),
            ("checkbox-checked-symbolic", None, "task-list", "Checklist"),
            (None, "“ ”", "quote", "Quote"),
            (None, "</>", "code", "Inline Code"),
            ("insert-link-symbolic", None, "link", "Link (Ctrl+K)"),
        ):
            button = Gtk.Button(action_name=f"win.{action}", tooltip_text=tip)
            if icon:
                button.set_icon_name(icon)
            else:
                button.set_label(label)
            button.add_css_class("flat")
            formatting.append(button)
        # Only show the formatting buttons when there is room; the keyboard
        # shortcuts still work in a narrow window.
        self.formatting = formatting
        header.pack_start(formatting)

        find = Gtk.Button(
            icon_name="edit-find-symbolic", action_name="win.find", tooltip_text="Find (Ctrl+F)"
        )
        header.pack_end(find)

        empty = Adw.StatusPage(
            icon_name="accessories-text-editor-symbolic",
            title="No Note Open",
            description="Pick a note in the sidebar, or start a new one.",
        )
        start = Gtk.Button(label="New Note", halign=Gtk.Align.CENTER)
        start.add_css_class("pill")
        start.add_css_class("suggested-action")
        start.set_detailed_action_name("win.new-note('')")
        empty.set_child(start)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(empty, "empty")
        self.stack.add_named(self.editor, "editor")

        self.toasts = Adw.ToastOverlay(child=self.stack)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        return Adw.NavigationPage(title="Note", child=view)

    def _install_actions(self):
        for name, handler in (
            ("new-note", self._on_new_note),
            ("new-folder", self._on_new_folder),
            ("rename", self._on_rename),
            ("trash", self._on_trash),
            ("show-in-files", self._on_show_in_files),
        ):
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            action.connect("activate", handler)
            self.add_action(action)

        for name, handler in (
            ("change-folder", self._on_change_folder),
            ("open-folder", self._on_open_folder),
            ("save", lambda *_: self.editor.save_now()),
            ("find", lambda *_: self.editor.show_find()),
            ("shortcuts", self._on_shortcuts),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

        self.format_actions = []
        for name, (method, *args) in FORMAT_ACTIONS.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, m=method, a=args: getattr(self.editor, m)(*a))
            self.add_action(action)
            self.format_actions.append(action)
        self.lookup_action("find").set_enabled(False)
        self._set_editing(False)

    # Notes folder --------------------------------------------------------

    def load_notes_dir(self, directory):
        directory = Path(directory).expanduser()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.toast(f"Couldn't open the notes folder: {error.strerror}")
            return
        self.notes_dir = directory
        self.sidebar.set_root(directory)
        self.split.get_sidebar().set_title(directory.name)

    def _on_change_folder(self, *_args):
        dialog = Gtk.FileDialog(title="Choose Notes Folder", modal=True)
        dialog.set_initial_folder(Gio.File.new_for_path(str(self.notes_dir)))
        dialog.select_folder(self, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return  # Cancelled.
        self.close_note()
        self.config.notes_dir = folder.get_path()
        self.config.save()
        self.load_notes_dir(folder.get_path())

    def _on_open_folder(self, *_args):
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(self.notes_dir))).launch(self, None, None)

    def _on_show_in_files(self, _action, param):
        target = Gio.File.new_for_uri(param.get_string())
        Gtk.FileLauncher.new(target).open_containing_folder(self, None, None)

    # Opening notes -------------------------------------------------------

    def open_note(self, path):
        path = Path(path)
        if self.editor.path == path:
            self.split.set_show_content(True)
            return
        try:
            self.editor.open(path)
        except (store.NoteError, OSError) as error:
            self.toast(str(error) if isinstance(error, store.NoteError) else error.strerror)
            return
        self.stack.set_visible_child_name("editor")
        self._set_editing(True)
        self._update_title()
        self.split.set_show_content(True)

    def close_note(self, save=True):
        self.editor.close(save=save)
        self.stack.set_visible_child_name("empty")
        self._set_editing(False)
        self._update_title()

    def _set_editing(self, editing):
        for action in self.format_actions:
            action.set_enabled(editing)
        self.lookup_action("find").set_enabled(editing)
        self.formatting.set_sensitive(editing)

    def _update_title(self):
        path = self.editor.path
        if path is None:
            self.window_title.set_title("")
            self.window_title.set_subtitle("")
            self.split.get_content().set_title("Note")
            return
        title = store.note_title(path)
        folder = path.parent.relative_to(self.notes_dir)
        self.window_title.set_title(title)
        self.window_title.set_subtitle("" if folder == Path(".") else str(folder))
        self.split.get_content().set_title(title)

    def _on_note_selected(self, _sidebar, gfile):
        self.open_note(gfile.get_path())

    def _on_editor_renamed(self, _editor, _old, new):
        self._update_title()
        self.sidebar.refresh()
        self.sidebar.select_file(Gio.File.new_for_path(str(new)))

    # Creating, renaming, moving, deleting --------------------------------

    def _target_folder(self, param):
        """The folder a "new" action should create in."""
        uri = param.get_string()
        gfile = Gio.File.new_for_uri(uri) if uri else self.sidebar.selected_file()
        if gfile is None:
            if self.editor.path:
                return self.editor.path.parent
            return self.notes_dir
        path = Path(gfile.get_path())
        return path if path.is_dir() else path.parent

    def _on_new_note(self, _action, param):
        try:
            path = store.create_note(self._target_folder(param))
        except (store.NoteError, OSError) as error:
            self.toast(f"Couldn't create a note: {error}")
            return
        self.sidebar.refresh()
        self.open_note(path)
        self.sidebar.select_file(Gio.File.new_for_path(str(path)))
        self.editor.focus_title()

    def _on_new_folder(self, _action, param):
        parent = self._target_folder(param)

        def create(name):
            folder = store.create_folder(parent, name)
            self.sidebar.refresh()
            self.sidebar.select_file(Gio.File.new_for_path(str(folder)))

        self._ask_name("New Folder", "Create", "New Folder", create)

    def _on_rename(self, _action, param):
        path = Path(Gio.File.new_for_uri(param.get_string()).get_path())
        if path == self.editor.path:
            self.split.set_show_content(True)
            self.editor.focus_title()
            return

        def rename(name):
            self.editor.save_now()
            new = store.rename(path, name)
            self.editor.relocate(path, new)
            self._update_title()
            self.sidebar.refresh()
            self.sidebar.select_file(Gio.File.new_for_path(str(new)))

        heading = "Rename Folder" if path.is_dir() else "Rename Note"
        self._ask_name(heading, "Rename", store.note_title(path), rename)

    def _on_move_requested(self, _sidebar, gfile, destination):
        path, folder = Path(gfile.get_path()), Path(destination.get_path())
        self.editor.save_now()
        try:
            new = store.move(path, folder)
        except (store.NoteError, OSError) as error:
            self.toast(str(error))
            return
        if new != path:
            self.editor.relocate(path, new)
            self._update_title()
            self.sidebar.refresh()
            self.sidebar.select_file(Gio.File.new_for_path(str(new)))

    def _on_trash(self, _action, param):
        gfile = Gio.File.new_for_uri(param.get_string())
        path = Path(gfile.get_path())
        kind = "folder" if path.is_dir() else "note"
        dialog = Adw.AlertDialog(
            heading=f"Move “{store.note_title(path)}” to the Trash?",
            body="You can restore it from the Trash in your file manager."
            + (" Everything inside the folder goes with it." if kind == "folder" else ""),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("trash", "Move to Trash")
        dialog.set_response_appearance("trash", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dialog, response):
            if response != "trash":
                return
            open_note = self.editor.path
            if open_note and store.is_inside(open_note, path):
                self.close_note(save=False)
            try:
                gfile.trash(None)
            except GLib.Error as error:
                self.toast(f"Couldn't move it to the Trash: {error.message}")
            self.sidebar.refresh()

        dialog.connect("response", on_response)
        dialog.present(self)

    def _ask_name(self, heading, verb, initial, apply):
        """Ask for a name, then call ``apply(name)``; errors become toasts."""
        dialog = Adw.AlertDialog(heading=heading)
        entry = Gtk.Entry(text=initial, activates_default=True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", verb)
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")

        def on_response(_dialog, response):
            if response != "ok":
                return
            try:
                apply(entry.get_text())
            except store.NoteError as error:
                self.toast(str(error))
            except OSError as error:
                self.toast(error.strerror or str(error))

        dialog.connect("response", on_response)
        dialog.present(self)
        entry.grab_focus()
        entry.select_region(0, -1)

    # Misc ----------------------------------------------------------------

    def toast(self, message):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(message), timeout=4))

    def _on_shortcuts(self, *_args):
        rows = (
            ("Ctrl+N", "New note"),
            ("Ctrl+Shift+N", "New folder"),
            ("Ctrl+S", "Save now (notes also save as you type)"),
            ("Ctrl+F", "Find in note"),
            ("Ctrl+B", "Bold"),
            ("Ctrl+I", "Italic"),
            ("Ctrl+H", "Heading"),
            ("Ctrl+K", "Link"),
            ("Ctrl+Z / Ctrl+Shift+Z", "Undo / redo"),
            ("Ctrl+Plus / Ctrl+Minus", "Zoom in / out"),
            ("Ctrl+0", "Reset zoom"),
            ("Ctrl+,", "Preferences"),
            ("Ctrl+Q", "Quit"),
        )
        group = Adw.PreferencesGroup()
        for keys, what in rows:
            row = Adw.ActionRow(title=what)
            label = Gtk.Label(label=keys)
            label.add_css_class("dim-label")
            row.add_suffix(label)
            group.add(row)
        page = Adw.PreferencesPage()
        page.add(group)
        header = Adw.HeaderBar()
        view = Adw.ToolbarView(content=page)
        view.add_top_bar(header)
        dialog = Adw.Dialog(title="Keyboard Shortcuts", child=view, content_width=420)
        dialog.present(self)

    def _on_close_request(self, *_args):
        self.editor.save_now()
        self.config.set("maximized", self.is_maximized())
        if not self.is_maximized():
            width, height = self.get_default_size()
            self.config.set("width", width)
            self.config.set("height", height)
        if self.editor.path:
            self.config.set("last_note", str(self.editor.path.relative_to(self.notes_dir)))
        else:
            self.config.set("last_note", None)
        self.config.save()
        return False

