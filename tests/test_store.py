import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inkwell import store  # noqa: E402


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_create_note_picks_unused_name(self):
        first = store.create_note(self.root)
        second = store.create_note(self.root)
        self.assertEqual(first.name, "Untitled.md")
        self.assertEqual(second.name, "Untitled 2.md")

    def test_create_folder(self):
        folder = store.create_folder(self.root, "Work")
        self.assertTrue(folder.is_dir())
        self.assertEqual(store.create_folder(self.root, "Work").name, "Work 2")

    def test_rename_note_keeps_suffix(self):
        note = store.create_note(self.root)
        renamed = store.rename(note, "Groceries")
        self.assertEqual(renamed.name, "Groceries.md")
        self.assertEqual(store.rename(renamed, "Shopping.md").name, "Shopping.md")

    def test_rename_refuses_existing_name(self):
        store.create_note(self.root, "A")
        b = store.create_note(self.root, "B")
        with self.assertRaises(store.NoteError):
            store.rename(b, "A")

    def test_rejects_bad_names(self):
        for name in ("", "  ", "a/b", ".hidden", ".."):
            with self.subTest(name=name), self.assertRaises(store.NoteError):
                store.clean_name(name)

    def test_move_note_into_folder(self):
        note = store.create_note(self.root, "Plan")
        folder = store.create_folder(self.root, "Work")
        moved = store.move(note, folder)
        self.assertEqual(moved, folder / "Plan.md")
        self.assertFalse(note.exists())

    def test_move_folder_into_itself_is_refused(self):
        outer = store.create_folder(self.root, "Outer")
        inner = store.create_folder(outer, "Inner")
        with self.assertRaises(store.NoteError):
            store.move(outer, inner)
        with self.assertRaises(store.NoteError):
            store.move(outer, outer)

    def test_move_refuses_to_overwrite(self):
        folder = store.create_folder(self.root, "Work")
        store.create_note(folder, "Plan")
        note = store.create_note(self.root, "Plan")
        with self.assertRaises(store.NoteError):
            store.move(note, folder)
        self.assertTrue(note.exists())

    def test_write_and_read_round_trip(self):
        note = store.create_note(self.root)
        store.write_note(note, "# Title\n\nCafé ☕\n")
        self.assertEqual(store.read_note(note), "# Title\n\nCafé ☕\n")
        self.assertEqual([p.name for p in self.root.iterdir()], ["Untitled.md"])

    def test_write_keeps_permissions(self):
        note = store.create_note(self.root)
        os.chmod(note, 0o600)
        store.write_note(note, "secret")
        self.assertEqual(note.stat().st_mode & 0o777, 0o600)

    def test_read_rejects_binary(self):
        note = self.root / "bad.md"
        note.write_bytes(b"\xff\xfe\x00")
        with self.assertRaises(store.NoteError):
            store.read_note(note)

    def test_note_title(self):
        self.assertEqual(store.note_title("a/Plan.md"), "Plan")
        self.assertEqual(store.note_title("a/Folder"), "Folder")


if __name__ == "__main__":
    unittest.main()
