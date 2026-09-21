"""The drawn icons, checked against the thing that made them necessary.

A tray never says what colour it is painting over, so the only question worth
asking of these pixmaps is whether they can be seen at all: a glyph drawn in
black on i3's black bar is an empty slot, which is what issue #27 was. So the
test blends each icon onto a bar of its own and asks whether anything of it
survives, once over black and once over white.
"""

import pathlib
import struct
import sys
import tempfile
import unittest
from unittest import mock

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from dikte import trayicon
from tests.support import DikteTest

# One application for the whole run; Qt allows no second one.
_app = QApplication.instance() or QApplication([])

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
# Breeze's own panel, as the middle case: not every bar is at one end.
CHARCOAL = (0x31, 0x36, 0x3B)


def _pixels(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(image.height()):
        for x in range(image.width()):
            yield image.pixelColor(x, y)


def _stands_out_from(pixmap, background):
    """True when some pixel of this icon differs from the bar behind it.

    The icons are transparent everywhere they are not drawn, so the tray gets
    the blend rather than the pixmap, and a pixel that blends back into the bar
    is a pixel nobody sees. 60 out of 255 is the gap being asked for, which is
    well under black against white and well over the antialiasing at an edge.
    """
    for colour in _pixels(pixmap):
        weight = colour.alphaF()
        ink = (colour.red(), colour.green(), colour.blue())
        for channel, behind in zip(ink, background):
            if abs(channel * weight + behind * (1 - weight) - behind) > 60:
                return True
    return False


def _drawn(pixmap):
    """True when anything at all was painted onto this pixmap."""
    return any(colour.alpha() > 128 for colour in _pixels(pixmap))


class Tray(DikteTest):
    """The four state icons, on a session whose theme has none of them."""

    def setUp(self):
        super().setUp()
        # Held between calls on purpose, so a test does not read what the one
        # before it drew on another platform.
        self.patch_attr(trayicon, "_cache", {})

    def test_a_name_we_do_not_draw_is_a_null_icon(self):
        # app.py asks the theme first and falls through to here, so anything
        # answered with a picture would be one the theme should have given.
        self.assertTrue(trayicon.icon("emblem-important").isNull())

    def test_every_state_has_a_shape(self):
        for name in trayicon.SHAPES:
            with self.subTest(name=name):
                icon = trayicon.icon(name)
                self.assertFalse(icon.isNull())
                for size in trayicon.SIZES:
                    self.assertTrue(_drawn(icon.pixmap(size, size)))

    def test_visible_on_a_bar_of_any_colour(self):
        # The regression: on X11 the icon is composited over a bar whose colour
        # nobody declares, and i3's is black.
        with mock.patch.object(sys, "platform", "linux"):
            for name in trayicon.SHAPES:
                for size in trayicon.SIZES:
                    pixmap = trayicon.icon(name).pixmap(size, size)
                    for background in (BLACK, WHITE, CHARCOAL):
                        with self.subTest(name=name, size=size, bar=background):
                            self.assertTrue(_stands_out_from(pixmap, background))

    def test_x11_is_not_handed_a_mask(self):
        # Only macOS recolours one. Setting it elsewhere would promise a
        # recolouring that never comes, and the outline would be the only thing
        # keeping the icon visible either way.
        with mock.patch.object(sys, "platform", "linux"):
            self.assertFalse(trayicon.icon("media-record").isMask())

    def test_macos_gets_a_flat_black_stencil(self):
        # There the colour is thrown away and only the coverage is read, so an
        # outline would come back as part of the glyph.
        with mock.patch.object(sys, "platform", "darwin"):
            icon = trayicon.icon("audio-input-microphone")
            self.assertTrue(icon.isMask())
            for colour in _pixels(icon.pixmap(22, 22)):
                if colour.alpha() > 128:
                    self.assertEqual(
                        (colour.red(), colour.green(), colour.blue()), BLACK)

    def test_the_two_platforms_do_not_share_a_cached_icon(self):
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertTrue(trayicon.icon("media-record").isMask())
        with mock.patch.object(sys, "platform", "linux"):
            self.assertFalse(trayicon.icon("media-record").isMask())


class ApplicationIcon(DikteTest):
    """The picture the menu entry, the task bar and the Finder are given."""

    def test_written_where_every_desktop_looks(self):
        with tempfile.TemporaryDirectory() as root:
            written = trayicon.write_hicolor(root)
            self.assertEqual(len(written), len(trayicon.HICOLOR_SIZES))
            for size, path in zip(trayicon.HICOLOR_SIZES, written):
                with self.subTest(size=size):
                    self.assertEqual(
                        path.parts[-3:], (f"{size}x{size}", "apps", "dikte.png"))
                    self.assertTrue(path.is_file())
                    image = QImage(str(path))
                    self.assertEqual((image.width(), image.height()),
                                     (size, size))

    def test_the_installed_name_is_the_one_the_entries_use(self):
        # install.sh writes Icon=dikte into both .desktop files, and a name that
        # matches no installed file is the blank slot all over again.
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(
                all(path.name == "dikte.png"
                    for path in trayicon.write_hicolor(root)))

    def test_a_tile_rather_than_a_stencil(self):
        # Coloured on purpose: this one is composited onto backgrounds that are
        # nothing like a tray, so it carries its own ground.
        pixmap = trayicon.app_pixmap(64)
        for background in (BLACK, WHITE):
            self.assertTrue(_stands_out_from(pixmap, background))

    def test_offered_at_the_sizes_a_window_asks_for(self):
        icon = trayicon.app_icon()
        self.assertFalse(icon.isNull())
        self.assertIn(48, [size.width() for size in icon.availableSizes()])

    def test_the_windows_icon_is_one_file_holding_every_size(self):
        """Written by hand, so the header is what a test can be wrong about:
        Windows reads the sizes out of the directory at the front rather than
        out of the images, and a 256 is written there as a zero."""
        with tempfile.TemporaryDirectory() as root:
            path = trayicon.write_ico(pathlib.Path(root) / "Dikte.ico")
            data = path.read_bytes()
            reserved, kind, count = struct.unpack_from("<HHH", data)
            self.assertEqual((reserved, kind), (0, 1))
            self.assertEqual(count, len(trayicon.ICO_SIZES))
            for index, size in enumerate(trayicon.ICO_SIZES):
                with self.subTest(size=size):
                    (width, height, _, _, _, _,
                     length, offset) = struct.unpack_from("<BBBBHHII", data,
                                                          6 + 16 * index)
                    self.assertEqual((width, height), (size % 256, size % 256))
                    image = QImage.fromData(data[offset:offset + length])
                    self.assertEqual((image.width(), image.height()),
                                     (size, size))


if __name__ == "__main__":
    unittest.main()
