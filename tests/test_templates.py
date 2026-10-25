import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inkwell import templates  # noqa: E402
from inkwell.templates import Template  # noqa: E402

NOW = datetime(2026, 10, 25, 21, 30)


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name) / "Stargazing Log"
        self.folder.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_parse_and_serialize_round_trip(self):
        template = Template("{{date}}", "Weather:\nTemperature:\n")
        text = templates.serialize(template)
        self.assertEqual(text, "---\ntitle: {{date}}\n---\nWeather:\nTemperature:\n")
        self.assertEqual(templates.parse(text), template)

    def test_template_without_title(self):
        self.assertEqual(templates.serialize(Template("", "Hi\n")), "Hi\n")
        self.assertEqual(templates.parse("Hi\n"), Template("", "Hi\n"))

    def test_horizontal_rule_later_is_not_front_matter(self):
        text = "Notes\n---\nMore\n"
        self.assertEqual(templates.parse(text), Template("", text))

    def test_title_placeholders(self):
        def title(pattern):
            return templates.note_title(Template(pattern), self.folder, NOW)

        self.assertEqual(title("{{date}}"), "2026-10-25")
        self.assertEqual(title("{{date:%d %B %Y}} at {{time}}"), "25 October 2026 at 21:30")
        self.assertEqual(title("{{folder}} {{date}}"), "Stargazing Log 2026-10-25")
        self.assertEqual(title("{{date:%Y/%m/%d}}"), "2026-10-25")
        self.assertEqual(title(""), "Untitled")
        self.assertEqual(title(".hidden"), "hidden")
        self.assertEqual(title("{{unknown}}"), "{{unknown}}")

    def test_body_and_cursor(self):
        body = "# {{title}}\nWeather: {{cursor}}\nTemperature:\n"
        text, cursor = templates.note_text(Template("", body), self.folder, "Tonight", NOW)
        self.assertEqual(text, "# Tonight\nWeather: \nTemperature:\n")
        self.assertEqual(cursor, len("# Tonight\nWeather: "))
        text, cursor = templates.note_text(Template("", "Weather:\nTemp:\n"), self.folder, "x", NOW)
        self.assertEqual(cursor, len("Weather:"))

    def test_create_note_from_template(self):
        templates.save(self.folder, Template("{{date}}", "Weather:\nMain Focus:\n"))
        first, cursor = templates.create_note(self.folder, NOW)
        second, _ = templates.create_note(self.folder, NOW)
        self.assertEqual(first.name, "2026-10-25.md")
        self.assertEqual(second.name, "2026-10-25 2.md")
        self.assertEqual(first.read_text(), "Weather:\nMain Focus:\n")
        self.assertEqual(cursor, len("Weather:"))

    def test_create_note_without_template(self):
        path, cursor = templates.create_note(self.folder, NOW)
        self.assertEqual(path.name, "Untitled.md")
        self.assertIsNone(cursor)
        self.assertEqual(path.read_text(), "")

    def test_template_is_only_for_its_own_folder(self):
        templates.save(self.folder, Template("{{date}}", "Weather:\n"))
        sub = self.folder / "Photos"
        sub.mkdir()
        path, _ = templates.create_note(sub, NOW)
        self.assertEqual(path.name, "Untitled.md")


if __name__ == "__main__":
    unittest.main()
