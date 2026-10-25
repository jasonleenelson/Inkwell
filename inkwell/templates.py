"""Per-folder note templates.

A folder can hold a hidden ``.template.md`` file. New notes made in that
folder start with its text, and can take their title from it too:

    ---
    title: {{date}}
    ---
    Weather:
    Temperature:

The part between the ``---`` lines is optional. Placeholders in the title
and the text are filled in when the note is made; see ``PLACEHOLDERS``.
Nothing in here depends on GTK, which keeps it easy to test.
"""

import re
from datetime import datetime
from pathlib import Path

from . import store

TEMPLATE_NAME = ".template.md"
DEFAULT_TITLE = "Untitled"

# Shown in the template dialog, so keep it in step with ``_fill``.
PLACEHOLDERS = (
    ("{{date}}", "Today's date, like 2026-10-25"),
    ("{{time}}", "The time, like 21:30"),
    ("{{date:%A %d %B}}", "The date in your own format, like Sunday 25 October"),
    ("{{title}}", "The new note's title"),
    ("{{folder}}", "The folder's name"),
    ("{{cursor}}", "Where the cursor starts in the new note"),
)

CURSOR = "{{cursor}}"
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)(?::([^}]*))?\s*\}\}")
_FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?)^---[ \t]*(?:\n|\Z)", re.DOTALL | re.MULTILINE)


class Template:
    def __init__(self, title="", body=""):
        self.title = title
        self.body = body

    def __eq__(self, other):
        return isinstance(other, Template) and (self.title, self.body) == (other.title, other.body)

    def __repr__(self):
        return f"Template(title={self.title!r}, body={self.body!r})"


def template_path(folder):
    return Path(folder) / TEMPLATE_NAME


def parse(text):
    """Split a template file into its title pattern and its body."""
    title = ""
    match = _FRONT_MATTER.match(text)
    if match:
        for line in match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip().lower() == "title":
                title = value.strip()
        text = text[match.end() :]
    return Template(title, text)


def serialize(template):
    title = template.title.strip()
    if not title:
        return template.body
    return f"---\ntitle: {title}\n---\n{template.body}"


def load(folder):
    """The folder's template, or ``None`` if it has none (or it can't be read)."""
    try:
        return parse(template_path(folder).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def save(folder, template):
    store.write_note(template_path(folder), serialize(template))


def _fill(text, now, values):
    def replace(match):
        name, fmt = match.group(1).lower(), match.group(2)
        if name in ("date", "time") and fmt:
            return now.strftime(fmt.strip())
        if name == "date":
            return now.strftime("%Y-%m-%d")
        if name == "time":
            return now.strftime("%H:%M")
        if name in values:
            return values[name]
        return match.group(0)  # Unknown, and {{cursor}}: leave for later.

    return _PLACEHOLDER.sub(replace, text)


def note_title(template, folder, now=None):
    """The title a new note in ``folder`` gets, made safe for a file name."""
    now = now or datetime.now()
    title = _fill(template.title, now, {"folder": Path(folder).name, "title": ""})
    title = title.replace(CURSOR, "").replace("/", "-").replace("\0", "")
    title = title.strip().lstrip(".").strip()
    return title or DEFAULT_TITLE


def note_text(template, folder, title, now=None):
    """The new note's text, and where the cursor goes (a character offset)."""
    now = now or datetime.now()
    text = _fill(template.body, now, {"folder": Path(folder).name, "title": title})
    cursor = text.find(CURSOR)
    if cursor >= 0:
        text = text.replace(CURSOR, "")
    else:
        # Start at the end of the first line, ready to fill in "Weather:".
        cursor = text.find("\n")
        if cursor < 0:
            cursor = len(text)
    return text, cursor


def create_note(folder, now=None):
    """Make a new note in ``folder`` from its template, if it has one.

    Returns ``(path, cursor)``; ``cursor`` is ``None`` when there was no
    template, so the caller can put the focus on the title instead.
    """
    template = load(folder)
    if template is None:
        return store.create_note(folder), None
    now = now or datetime.now()
    title = note_title(template, folder, now)
    path = store.unique_path(folder, title, store.NOTE_SUFFIX)
    text, cursor = note_text(template, folder, store.note_title(path), now)
    with open(path, "x", encoding="utf-8") as handle:
        handle.write(text)
    return path, cursor
