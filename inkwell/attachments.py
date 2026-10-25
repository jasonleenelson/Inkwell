"""The strip of attached pictures and files along the bottom of a note.

Attachments are ordinary files in a folder beside the note (see
``store.attachments_dir``), so the Markdown file itself stays untouched.
"""

import threading
from pathlib import Path

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk, Pango

from . import store

TILE_WIDTH = 112
THUMB_HEIGHT = 80


def is_image(path):
    content_type, _uncertain = Gio.content_type_guess(str(path), None)
    return Gio.content_type_is_a(content_type, "image/*")


def load_thumbnail(path, width, height):
    """A downscaled texture of the picture at ``path``, or None. Thread-safe."""
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), width, height, True)
    except GLib.Error:
        return None
    # Phone photos are often stored sideways with an EXIF note to rotate them.
    pixbuf = pixbuf.apply_embedded_orientation() or pixbuf
    memory_format = (
        Gdk.MemoryFormat.R8G8B8A8 if pixbuf.get_has_alpha() else Gdk.MemoryFormat.R8G8B8
    )
    return Gdk.MemoryTexture.new(
        pixbuf.get_width(),
        pixbuf.get_height(),
        memory_format,
        pixbuf.read_pixel_bytes(),
        pixbuf.get_rowstride(),
    )


class Thumbnail(Gtk.Picture):
    """A picture that always takes the tile's size, whatever the image's."""

    def do_measure(self, orientation, _for_size):
        size = TILE_WIDTH if orientation == Gtk.Orientation.HORIZONTAL else THUMB_HEIGHT
        return size, size, -1, -1


class AttachmentStrip(Gtk.Box):
    """Thumbnails of a note's attachments; click one to open it."""

    __gsignals__ = {
        "error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, visible=False)
        self.note = None
        self._generation = 0
        self.add_css_class("attachments")

        self.append(Gtk.Separator())
        self.heading = Gtk.Label(xalign=0)
        self.heading.add_css_class("caption-heading")
        self.heading.add_css_class("dim-label")
        self.tiles = Gtk.Box(spacing=6)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        column.append(self.heading)
        column.append(self.tiles)
        scroller = Gtk.ScrolledWindow(child=column)
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.append(Adw.Clamp(child=scroller, maximum_size=760, tightening_threshold=600))

        actions = Gio.SimpleActionGroup()
        for name, handler in (
            ("open", self._on_open),
            ("show", self._on_show),
            ("remove", self._on_remove),
        ):
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            action.connect("activate", handler)
            actions.add_action(action)
        self.insert_action_group("attachment", actions)

    # Contents ------------------------------------------------------------

    def set_note(self, note):
        self.note = Path(note) if note else None
        self.refresh()

    def refresh(self):
        self._generation += 1
        while child := self.tiles.get_first_child():
            self.tiles.remove(child)
        files = store.list_attachments(self.note) if self.note else []
        self.set_visible(bool(files))
        count = len(files)
        self.heading.set_label(f"{count} attachment" + ("" if count == 1 else "s"))
        pictures = []
        for path in files:
            tile, picture = self._make_tile(path)
            self.tiles.append(tile)
            if picture is not None:
                pictures.append((path, picture))
        if pictures:
            scale = self.get_scale_factor()
            threading.Thread(
                target=self._load_thumbnails,
                args=(self._generation, pictures, TILE_WIDTH * scale, THUMB_HEIGHT * scale),
                daemon=True,
            ).start()

    def _load_thumbnails(self, generation, pictures, width, height):
        for path, picture in pictures:
            texture = load_thumbnail(path, width, height)
            if texture is not None:
                GLib.idle_add(self._set_thumbnail, generation, picture, texture)

    def _set_thumbnail(self, generation, picture, texture):
        if generation == self._generation:
            picture.set_paintable(texture)
        return GLib.SOURCE_REMOVE

    def _make_tile(self, path):
        picture = None
        if is_image(path):
            picture = Thumbnail(content_fit=Gtk.ContentFit.COVER)
            preview = picture
        else:
            content_type, _uncertain = Gio.content_type_guess(str(path), None)
            preview = Gtk.Image.new_from_gicon(Gio.content_type_get_symbolic_icon(content_type))
            preview.set_pixel_size(40)
            preview.set_size_request(TILE_WIDTH, THUMB_HEIGHT)
        frame = Gtk.Frame(child=preview, overflow=Gtk.Overflow.HIDDEN)
        frame.add_css_class("attachment-preview")
        label = Gtk.Label(
            label=path.name,
            ellipsize=Pango.EllipsizeMode.MIDDLE,
            max_width_chars=1,
            hexpand=True,
        )
        label.add_css_class("caption")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(frame)
        box.append(label)
        button = Gtk.Button(child=box, tooltip_text=path.name)
        button.set_size_request(TILE_WIDTH, -1)
        button.add_css_class("flat")
        button.add_css_class("attachment")
        button.set_action_name("attachment.open")
        button.set_action_target_value(GLib.Variant("s", str(path)))

        menu_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        menu_click.connect("pressed", self._on_tile_menu, button, path)
        button.add_controller(menu_click)
        return button, picture

    def _on_tile_menu(self, gesture, _n_press, x, y, button, path):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        menu = Gio.Menu()
        for label, action in (
            ("Open", "attachment.open"),
            ("Show in Files", "attachment.show"),
            ("Move to Trash", "attachment.remove"),
        ):
            item = Gio.MenuItem.new(label, None)
            item.set_action_and_target_value(action, GLib.Variant("s", str(path)))
            menu.append_item(item)
        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_has_arrow(False)
        popover.set_parent(button)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        popover.connect("closed", lambda p: GLib.idle_add(p.unparent))
        popover.popup()

    # Adding --------------------------------------------------------------

    def add_files(self, gfiles):
        """Copy local files into the note's attachments. Returns how many."""
        if self.note is None:
            return 0
        added = 0
        for gfile in gfiles:
            path = gfile.get_path()
            if path is None or Path(path).is_dir():
                continue
            try:
                store.add_attachment(self.note, path)
                added += 1
            except store.NoteError as error:
                self.emit("error", str(error))
            except OSError as error:
                self.emit("error", f"Couldn't attach “{Path(path).name}”: {error.strerror}")
        if added:
            self.refresh()
        return added

    def add_texture(self, texture):
        """Save a pasted or dropped image as a new PNG attachment."""
        if self.note is None:
            return
        name = GLib.DateTime.new_now_local().format("Pasted image %Y-%m-%d %H%M%S.png")
        try:
            store.add_attachment_data(self.note, name, texture.save_to_png_bytes().get_data())
        except OSError as error:
            self.emit("error", f"Couldn't save the pasted image: {error.strerror}")
            return
        self.refresh()

    # Tile actions --------------------------------------------------------

    def _on_open(self, _action, param):
        gfile = Gio.File.new_for_path(param.get_string())
        Gtk.FileLauncher.new(gfile).launch(self.get_root(), None, None)

    def _on_show(self, _action, param):
        gfile = Gio.File.new_for_path(param.get_string())
        Gtk.FileLauncher.new(gfile).open_containing_folder(self.get_root(), None, None)

    def _on_remove(self, _action, param):
        path = Path(param.get_string())
        dialog = Adw.AlertDialog(
            heading=f"Move “{path.name}” to the Trash?",
            body="It's removed from this note. You can restore it from the Trash in your file manager.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("trash", "Move to Trash")
        dialog.set_response_appearance("trash", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dialog, response):
            if response != "trash":
                return
            try:
                Gio.File.new_for_path(str(path)).trash(None)
            except GLib.Error as error:
                self.emit("error", f"Couldn't move it to the Trash: {error.message}")
            if self.note:
                store.remove_empty_attachments_dir(self.note)
            self.refresh()

        dialog.connect("response", on_response)
        dialog.present(self.get_root())
