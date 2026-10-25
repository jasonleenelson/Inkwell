"""The folder tree on the left of the window."""

import os
from pathlib import Path

from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango

from . import store

REFRESH_DELAY_MS = 150


class Entry(GObject.Object):
    """One note or folder in the tree."""

    def __init__(self, path, folder):
        super().__init__()
        self.path = Path(path)
        self.folder = folder
        self.gfile = Gio.File.new_for_path(str(path))

    @property
    def key(self):
        # Folders first, then notes, each alphabetically.
        return (not self.folder, self.path.name.casefold(), self.path.name)


def file_of(entry):
    return entry.gfile


def is_folder(entry):
    return entry.folder


def list_folder(directory):
    """The visible notes and folders directly inside ``directory``, sorted."""
    entries = []
    try:
        with os.scandir(directory) as scan:
            for item in scan:
                if item.name.startswith(".") or item.name.endswith("~"):
                    continue
                try:
                    folder = item.is_dir()
                except OSError:
                    continue
                if folder or item.name.lower().endswith(store.NOTE_SUFFIX):
                    entries.append(Entry(item.path, folder))
    except OSError:
        pass
    return sorted(entries, key=lambda entry: entry.key)


class FolderModel:
    """A list model of one folder that keeps itself in step with the disk."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.store = Gio.ListStore(item_type=Entry)
        self._pending = 0
        self.monitor = None
        try:
            self.monitor = Gio.File.new_for_path(str(directory)).monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES, None
            )
            self.monitor.connect("changed", self._on_changed)
        except GLib.Error:
            pass
        self.refresh()

    def _on_changed(self, *_args):
        # Many events can arrive at once (a save is several), so batch them.
        if not self._pending:
            self._pending = GLib.timeout_add(REFRESH_DELAY_MS, self._refresh_soon)

    def _refresh_soon(self):
        self._pending = 0
        self.refresh()
        return GLib.SOURCE_REMOVE

    def refresh(self):
        """Update the list in place, so open folders below stay open."""
        wanted = list_folder(self.directory)
        wanted_keys = {entry.key for entry in wanted}
        for position in reversed(range(self.store.get_n_items())):
            if self.store.get_item(position).key not in wanted_keys:
                self.store.remove(position)
        for position, entry in enumerate(wanted):
            current = self.store.get_item(position)
            if current is None or current.key != entry.key:
                self.store.insert(position, entry)

    def close(self):
        if self.monitor:
            self.monitor.cancel()
        if self._pending:
            GLib.source_remove(self._pending)
            self._pending = 0


class Sidebar(Gtk.Box):
    """Shows the notes folder as an expandable tree of folders and notes.

    Each folder level watches the disk, so notes added, renamed or removed
    by any program show up on their own.
    """

    __gsignals__ = {
        "note-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "move-requested": (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.root = None
        self._models = {}
        self._pending_select = None

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind)
        factory.connect("unbind", self._on_unbind)

        self.selection = Gtk.SingleSelection(autoselect=False, can_unselect=True)
        self.selection.connect("selection-changed", self._on_selection_changed)

        self.list_view = Gtk.ListView(model=self.selection, factory=factory)
        self.list_view.add_css_class("navigation-sidebar")
        self.list_view.connect("activate", self._on_activate)

        scroller = Gtk.ScrolledWindow(vexpand=True, child=self.list_view)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroller)

        # Dropping onto empty space moves an item to the top of the notes folder.
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.MOVE)
        drop.connect("drop", lambda _t, value, _x, _y: self._on_drop(value, self.root))
        scroller.add_controller(drop)

        # Right-clicking empty space offers "new note" and "new folder".
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        click.connect("pressed", self._on_background_menu)
        scroller.add_controller(click)

    # Model ---------------------------------------------------------------

    def set_root(self, directory):
        for model in self._models.values():
            model.close()
        self._models = {}
        self.root = Gio.File.new_for_path(str(directory))
        tree = Gtk.TreeListModel.new(self._folder_model(directory), False, False, self._child_model)
        self.selection.set_model(tree)

    def refresh(self):
        """Re-read every folder now, rather than waiting for the disk monitor."""
        for directory, model in list(self._models.items()):
            if directory.is_dir():
                model.refresh()
            else:
                model.close()
                del self._models[directory]

    def _folder_model(self, directory):
        directory = Path(directory)
        model = self._models.get(directory)
        if model is None:
            model = self._models[directory] = FolderModel(directory)
        else:
            model.refresh()
        return model.store

    def _child_model(self, entry, *_args):
        if entry.folder:
            return self._folder_model(entry.path)
        return None

    # Rows ----------------------------------------------------------------

    def _on_setup(self, _factory, list_item):
        icon = Gtk.Image()
        label = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        box = Gtk.Box(spacing=8, hexpand=True)
        box.append(icon)
        box.append(label)
        expander = Gtk.TreeExpander(child=box)
        list_item.set_child(expander)
        expander.icon = icon
        expander.label = label
        expander.row = None

        # A single click on a folder opens or closes it, like Obsidian.
        click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
        click.connect("released", self._on_row_clicked, expander)
        box.add_controller(click)

        menu_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        menu_click.connect("pressed", self._on_row_menu, expander)
        expander.add_controller(menu_click)

        drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag.connect("prepare", self._on_drag_prepare, expander)
        expander.add_controller(drag)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.MOVE)
        drop.connect("drop", self._on_row_drop, expander)
        expander.add_controller(drop)

    def _on_bind(self, _factory, list_item):
        expander = list_item.get_child()
        row = list_item.get_item()
        expander.set_list_row(row)
        expander.row = row
        entry = row.get_item()
        icon = "folder-symbolic" if entry.folder else "text-x-generic-symbolic"
        expander.icon.set_from_icon_name(icon)
        expander.label.set_label(store.note_title(entry.path))
        expander.set_tooltip_text(str(entry.path))

    def _on_unbind(self, _factory, list_item):
        expander = list_item.get_child()
        expander.set_list_row(None)
        expander.row = None

    def _on_row_clicked(self, _gesture, n_press, _x, _y, expander):
        row = expander.row
        if row and n_press == 1 and is_folder(row.get_item()):
            row.set_expanded(not row.get_expanded())

    def _on_activate(self, _view, position):
        row = self.selection.get_model().get_item(position)
        if row and not is_folder(row.get_item()):
            self.emit("note-selected", file_of(row.get_item()))

    def _on_selection_changed(self, *_args):
        row = self.selection.get_selected_item()
        if row and not is_folder(row.get_item()):
            self.emit("note-selected", file_of(row.get_item()))

    # Context menus -------------------------------------------------------

    def _on_row_menu(self, gesture, _n_press, x, y, expander):
        row = expander.row
        if row is None:
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        entry = row.get_item()
        uri = file_of(entry).get_uri()
        menu = Gio.Menu()
        create = Gio.Menu()
        create.append_item(_item("New Note", "win.new-note", uri))
        create.append_item(_item("New Folder", "win.new-folder", uri))
        if entry.folder:
            create.append_item(_item("Note Template…", "win.edit-template", uri))
        menu.append_section(None, create)
        edit = Gio.Menu()
        edit.append_item(_item("Rename…", "win.rename", uri))
        edit.append_item(_item("Show in Files", "win.show-in-files", uri))
        edit.append_item(_item("Move to Trash", "win.trash", uri))
        menu.append_section(None, edit)
        self._popup(menu, expander, x, y)

    def _on_background_menu(self, gesture, _n_press, x, y):
        if self.root is None:
            return
        uri = self.root.get_uri()
        menu = Gio.Menu()
        menu.append_item(_item("New Note", "win.new-note", uri))
        menu.append_item(_item("New Folder", "win.new-folder", uri))
        menu.append_item(_item("Note Template…", "win.edit-template", uri))
        self._popup(menu, gesture.get_widget(), x, y)

    def _popup(self, menu, widget, x, y):
        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_has_arrow(False)
        popover.set_halign(Gtk.Align.START)
        popover.set_parent(widget)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        popover.connect("closed", lambda p: GLib.idle_add(p.unparent))
        popover.popup()

    # Drag and drop -------------------------------------------------------

    def _on_drag_prepare(self, _source, _x, _y, expander):
        if expander.row is None:
            return None
        files = Gdk.FileList.new_from_list([file_of(expander.row.get_item())])
        return Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.FileList, files))

    def _on_row_drop(self, _target, value, _x, _y, expander):
        if expander.row is None:
            return False
        entry = expander.row.get_item()
        destination = file_of(entry)
        if not is_folder(entry):
            destination = destination.get_parent()
        return self._on_drop(value, destination)

    def _on_drop(self, value, destination):
        if destination is None or self.root is None:
            return False
        handled = False
        for gfile in value.get_files():
            path = gfile.get_path()
            # Only items that already live in the notes folder are moved.
            if path and store.is_inside(path, self.root.get_path()):
                self.emit("move-requested", gfile, destination)
                handled = True
        return handled

    # Selection helpers ---------------------------------------------------

    def selected_file(self):
        row = self.selection.get_selected_item()
        return file_of(row.get_item()) if row else None

    def select_file(self, gfile, attempts=20):
        """Select ``gfile``, opening its parent folders on the way.

        Folder listings load in the background, so this retries briefly
        until the row appears.
        """
        self._pending_select = gfile
        GLib.timeout_add(50, self._try_select, gfile, attempts)

    def _try_select(self, gfile, attempts):
        if self._pending_select is not gfile:
            return False
        tree = self.selection.get_model()
        if tree is None:
            return False
        for position in range(tree.get_n_items()):
            row = tree.get_item(position)
            candidate = file_of(row.get_item())
            if candidate.equal(gfile):
                self.selection.set_selected(position)
                self.list_view.scroll_to(position, Gtk.ListScrollFlags.NONE, None)
                self._pending_select = None
                return False
            if gfile.has_prefix(candidate) and not row.get_expanded():
                row.set_expanded(True)
        if attempts <= 0:
            self._pending_select = None
            return False
        GLib.timeout_add(50, self._try_select, gfile, attempts - 1)
        return False


def _item(label, action, uri):
    item = Gio.MenuItem.new(label, None)
    item.set_action_and_target_value(action, GLib.Variant("s", uri))
    return item

