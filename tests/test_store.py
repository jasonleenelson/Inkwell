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


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.note = store.create_note(self.root, "Trip")
        self.photo = self.root / "outside" / "photo.jpg"
        self.photo.parent.mkdir()
        self.photo.write_bytes(b"jpeg")

    def tearDown(self):
        self._tmp.cleanup()

    def test_note_without_attachments(self):
        self.assertEqual(store.list_attachments(self.note), [])
        self.assertFalse(store.attachments_dir(self.note).exists())

    def test_add_copies_into_folder_beside_note(self):
        added = store.add_attachment(self.note, self.photo)
        self.assertEqual(added, self.root / "Trip.assets" / "photo.jpg")
        self.assertEqual(added.read_bytes(), b"jpeg")
        self.assertTrue(self.photo.exists())
        self.assertEqual(store.list_attachments(self.note), [added])

    def test_add_never_overwrites(self):
        first = store.add_attachment(self.note, self.photo)
        second = store.add_attachment(self.note, self.photo)
        self.assertEqual(second.name, "photo 2.jpg")
        self.assertEqual(len(store.list_attachments(self.note)), 2)
        self.assertTrue(first.exists())

    def test_add_data(self):
        added = store.add_attachment_data(self.note, "Pasted image.png", b"png")
        self.assertEqual(added.read_bytes(), b"png")
        again = store.add_attachment_data(self.note, "Pasted image.png", b"png2")
        self.assertEqual(again.name, "Pasted image 2.png")

    def test_attachments_folder_is_recognised(self):
        store.add_attachment(self.note, self.photo)
        self.assertTrue(store.is_attachments_dir(self.root / "Trip.assets"))
        (self.root / "Other.assets").mkdir()
        self.assertFalse(store.is_attachments_dir(self.root / "Other.assets"))

    def test_rename_carries_attachments(self):
        store.add_attachment(self.note, self.photo)
        renamed = store.rename(self.note, "Holiday")
        self.assertFalse((self.root / "Trip.assets").exists())
        self.assertEqual(
            [p.name for p in store.list_attachments(renamed)], ["photo.jpg"]
        )

    def test_rename_refuses_to_merge_attachments(self):
        store.add_attachment(self.note, self.photo)
        (self.root / "Holiday.assets").mkdir()
        with self.assertRaises(store.NoteError):
            store.rename(self.note, "Holiday")
        self.assertTrue(self.note.exists())
        self.assertTrue((self.root / "Trip.assets" / "photo.jpg").exists())

    def test_move_carries_attachments(self):
        store.add_attachment(self.note, self.photo)
        folder = store.create_folder(self.root, "Travel")
        moved = store.move(self.note, folder)
        self.assertEqual(moved, folder / "Trip.md")
        self.assertTrue((folder / "Trip.assets" / "photo.jpg").exists())
        self.assertFalse((self.root / "Trip.assets").exists())

    def test_remove_empty_folder_only(self):
        added = store.add_attachment(self.note, self.photo)
        store.remove_empty_attachments_dir(self.note)
        self.assertTrue(added.exists())
        added.unlink()
        store.remove_empty_attachments_dir(self.note)
        self.assertFalse(store.attachments_dir(self.note).exists())


if __name__ == "__main__":
    unittest.main()
