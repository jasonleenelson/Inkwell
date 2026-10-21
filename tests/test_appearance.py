import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inkwell import appearance  # noqa: E402


class AppearanceTests(unittest.TestCase):
    def test_zoom_steps_through_levels(self):
        self.assertEqual(appearance.zoom_in(100), 110)
        self.assertEqual(appearance.zoom_out(100), 90)

    def test_zoom_stops_at_the_ends(self):
        self.assertEqual(appearance.zoom_in(appearance.ZOOM_LEVELS[-1]), appearance.ZOOM_LEVELS[-1])
        self.assertEqual(appearance.zoom_out(appearance.ZOOM_LEVELS[0]), appearance.ZOOM_LEVELS[0])

    def test_stored_zoom_snaps_to_a_level(self):
        self.assertEqual(appearance.clamp_zoom(123), 125)
        self.assertEqual(appearance.clamp_zoom(1000), appearance.ZOOM_LEVELS[-1])
        self.assertEqual(appearance.clamp_zoom("junk"), appearance.DEFAULT_ZOOM)
        self.assertEqual(appearance.clamp_zoom(None), appearance.DEFAULT_ZOOM)

    def test_font_size_is_clamped(self):
        self.assertEqual(appearance.clamp_font_size(14.4), 14)
        self.assertEqual(appearance.clamp_font_size(1), appearance.MIN_FONT_SIZE)
        self.assertEqual(appearance.clamp_font_size(500), appearance.MAX_FONT_SIZE)
        self.assertEqual(appearance.clamp_font_size("big"), appearance.DEFAULT_FONT_SIZE)


if __name__ == "__main__":
    unittest.main()
