"""Small JSON settings file in the user's config directory."""

import json
import os
from pathlib import Path

from gi.repository import GLib

APP_DIR_NAME = "inkwell"


def config_path():
    return Path(GLib.get_user_config_dir()) / APP_DIR_NAME / "settings.json"


def default_notes_dir():
    documents = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
    base = Path(documents) if documents else Path.home()
    return base / "Notes"


class Config:
    def __init__(self, path=None):
        self.path = Path(path) if path else config_path()
        self.data = {}
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    @property
    def notes_dir(self):
        value = os.environ.get("INKWELL_NOTES_DIR") or self.data.get("notes_dir")
        return Path(value).expanduser() if value else default_notes_dir()

    @notes_dir.setter
    def notes_dir(self, value):
        self.data["notes_dir"] = str(value)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        except OSError as error:
            print(f"inkwell: could not save settings: {error}")
