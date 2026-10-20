"""Plain-file storage for notes.

Notes are Markdown files and folders are ordinary directories, so the notes
folder stays readable with any other tool. Nothing in here depends on GTK,
which keeps it easy to test.
"""

import os
import shutil
import tempfile
from pathlib import Path

NOTE_SUFFIX = ".md"


class NoteError(Exception):
    """A user-facing problem with a note or folder operation."""


def is_note(path):
    path = Path(path)
    return path.suffix.lower() == NOTE_SUFFIX and not path.is_dir()


def note_title(path):
    """The name shown for a note or folder: the file name without ``.md``."""
    path = Path(path)
    if path.suffix.lower() == NOTE_SUFFIX:
        return path.stem
    return path.name


def clean_name(name):
    """Validate a note or folder name typed by the user."""
    name = name.strip()
    if not name:
        raise NoteError("The name can't be empty.")
    if "/" in name or "\0" in name:
        raise NoteError("The name can't contain “/”.")
    if name in (".", ".."):
        raise NoteError("That name is reserved.")
    if name.startswith("."):
        raise NoteError("The name can't start with a dot, because it would be hidden.")
    return name


def unique_path(directory, stem, suffix=""):
    """Return ``directory/stem+suffix``, adding a number if it is taken."""
    directory = Path(directory)
    candidate = directory / f"{stem}{suffix}"
    number = 2
    while candidate.exists():
        candidate = directory / f"{stem} {number}{suffix}"
        number += 1
    return candidate


def create_note(directory, title="Untitled"):
    path = unique_path(directory, clean_name(title), NOTE_SUFFIX)
    path.touch(exist_ok=False)
    return path


def create_folder(directory, name="New Folder"):
    path = unique_path(directory, clean_name(name))
    path.mkdir()
    return path


def rename(path, new_name):
    """Rename a note or folder in place. Notes keep their ``.md`` suffix."""
    path = Path(path)
    new_name = clean_name(new_name)
    if not path.is_dir():
        if new_name.lower().endswith(NOTE_SUFFIX):
            new_name = new_name[: -len(NOTE_SUFFIX)].rstrip()
            new_name = clean_name(new_name)
        new_name += path.suffix
    target = path.with_name(new_name)
    if target == path:
        return path
    if target.exists():
        raise NoteError(f"“{note_title(target)}” already exists here.")
    path.rename(target)
    return target


def is_inside(path, directory):
    """True if ``path`` is ``directory`` or somewhere below it."""
    path = Path(path).resolve()
    directory = Path(directory).resolve()
    return path == directory or directory in path.parents


def move(path, destination):
    """Move a note or folder into the ``destination`` folder."""
    path = Path(path)
    destination = Path(destination)
    if not destination.is_dir():
        raise NoteError("Notes can only be moved into a folder.")
    if path.is_dir() and is_inside(destination, path):
        raise NoteError("A folder can't be moved into itself.")
    if path.parent.resolve() == destination.resolve():
        return path
    target = destination / path.name
    if target.exists():
        raise NoteError(f"“{note_title(target)}” already exists in that folder.")
    shutil.move(str(path), str(target))
    return target


def read_note(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise NoteError("This file isn't UTF-8 text, so it wasn't opened.") from None


def write_note(path, text):
    """Write a note atomically, so a crash never leaves half a file behind."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        if path.exists():
            shutil.copymode(path, tmp)
        else:
            os.chmod(tmp, 0o666 & ~_umask())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _umask():
    mask = os.umask(0)
    os.umask(mask)
    return mask
