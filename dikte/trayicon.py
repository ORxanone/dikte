"""The four tray icons, drawn here for systems that have no icon theme.

A desktop hands out `audio-input-microphone`, `media-record`, `view-refresh`
and `media-playback-pause` from whatever icon theme is installed, and Qt finds
them through QIcon.fromTheme. Two systems have nothing to hand out. macOS keeps
no such registry at all. And a Linux session that names no desktop, which is
what i3 and a bare X11 login are, leaves Qt with `hicolor` as its only theme,
where none of those four names exist. On both, fromTheme returns a null icon,
and a null icon in a tray is an item you cannot see, which is the whole of
Dikte's interface gone. So the same four shapes are drawn here, and used
whenever the theme has nothing to offer.

On macOS they are template images: one colour, transparent everywhere else,
with isMask set. That is what lets macOS invert them for a dark menu bar and
grey them while the menu is open, and it is why the shapes are outlines rather
than the coloured glyphs a Linux theme would give.

X11 has no such contract. A tray there is given a picture, paints it over
whatever colour the bar happens to be, and never says what that colour is, so
black ink on i3's black bar is an empty slot rather than an icon. The same
shapes are drawn there in white over a dark copy of themselves spread a pixel
outwards, which stands out on a dark bar and stays readable on a light one.
"""

import pathlib
import struct
import sys

from PyQt6.QtCore import QBuffer, QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QIcon, QLinearGradient, QPainter, QPainterPath,
                         QPen, QPixmap)

# What a Mac menu bar asks for: 22 points, at 1x and at 2x. Both are put in the
# icon rather than one being scaled, because a scaled stroke goes soft.
SIZES = (22, 44)
# The two inks. macOS is handed the dark one and throws the colour away, keeping
# only the coverage; everywhere else the light one is the glyph and the dark one
# is the outline behind it.
DARK = QColor(0, 0, 0)
LIGHT = QColor(255, 255, 255)


def _canvas(size):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pixmap, painter


def _microphone(painter, size, ink):
    """A capsule on a stand: idle, and the application's own mark.

    Every shape below takes its colour rather than reaching for a constant: the
    same glyph is drawn dark for the macOS mask, white for the tray on X11, dark
    again a pixel out for the outline under it, and white on the blue tile of
    the application icon.
    """
    unit = size / 22.0
    pen = QPen(ink, 1.6 * unit)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(ink)
    # The capsule, held away from the edges so the stroke below has room.
    painter.drawRoundedRect(
        QRectF(8.2 * unit, 3.4 * unit, 5.6 * unit, 10.4 * unit),
        2.8 * unit, 2.8 * unit,
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # The arc that cradles it, and the post and foot under that.
    painter.drawArc(
        QRectF(5.4 * unit, 6.6 * unit, 11.2 * unit, 10.4 * unit),
        180 * 16, 180 * 16,
    )
    painter.drawLine(QPointF(11 * unit, 16.8 * unit), QPointF(11 * unit, 19 * unit))
    painter.drawLine(QPointF(7.6 * unit, 19 * unit), QPointF(14.4 * unit, 19 * unit))


def _record(painter, size, ink):
    """A filled dot: recording, and the same red dot the overlay shows."""
    unit = size / 22.0
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    painter.drawEllipse(QPointF(11 * unit, 11 * unit), 6.4 * unit, 6.4 * unit)


def _paused(painter, size, ink):
    """Two bars: the recording is still ours, and nothing is going into it."""
    unit = size / 22.0
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    for left in (6.4, 12.4):
        painter.drawRoundedRect(
            QRectF(left * unit, 5.0 * unit, 3.2 * unit, 12.0 * unit),
            1.2 * unit, 1.2 * unit,
        )


def _working(painter, size, ink):
    """An arrow chasing its own circle: transcribing, cleaning up, thinking."""
    unit = size / 22.0
    pen = QPen(ink, 2.0 * unit)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    ring = QRectF(4.4 * unit, 4.4 * unit, 13.2 * unit, 13.2 * unit)
    # Three quarters of the way round, leaving the gap the head sits in.
    painter.drawArc(ring, 90 * 16, -280 * 16)

    # The head, as a filled triangle at the open end rather than two more
    # strokes: at 22 points a drawn arrowhead closes up into a blob.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    head = QPainterPath()
    head.moveTo(QPointF(11.0 * unit, 1.6 * unit))
    head.lineTo(QPointF(11.0 * unit, 7.2 * unit))
    head.lineTo(QPointF(15.8 * unit, 4.4 * unit))
    head.closeSubpath()
    painter.drawPath(head)


# The names Linux themes use, which are what app.py asks for either way.
SHAPES = {
    "audio-input-microphone": _microphone,
    "media-record": _record,
    "media-playback-pause": _paused,
    "view-refresh": _working,
}

_cache = {}


def _stencil(shape, size, ink, pad=0):
    """One shape in one colour, held `pad` pixels in from every edge.

    The inset is what leaves room for the outline: the shapes are drawn to the
    edge of their 22 point square, so a copy shifted outwards would otherwise
    lose the foot of the microphone and the tip of the arrow to the crop.
    """
    pixmap, painter = _canvas(size)
    try:
        if pad:
            painter.translate(pad, pad)
            painter.scale((size - 2 * pad) / size, (size - 2 * pad) / size)
        shape(painter, size, ink)
    finally:
        painter.end()
    return pixmap


def _outlined(shape, size):
    """The shape in white, over a dark copy of itself spread a pixel outwards.

    Eight shifted copies rather than a blur or a stroked path: the shapes are a
    mix of strokes and fills, and this is the one way to put a border round all
    of them without drawing each one twice by hand.
    """
    pad = max(1, round(size / 22.0))
    outline = _stencil(shape, size, DARK, pad)
    glyph = _stencil(shape, size, LIGHT, pad)
    pixmap, painter = _canvas(size)
    try:
        for dx in (-pad, 0, pad):
            for dy in (-pad, 0, pad):
                painter.drawPixmap(dx, dy, outline)
        painter.drawPixmap(0, 0, glyph)
    finally:
        painter.end()
    return pixmap


def icon(name):
    """The named icon drawn here, or a null QIcon when it is not one of ours.

    Cached because the tray is refreshed on every state change and every one of
    those would otherwise redraw three pixmaps. A QIcon is cheap to copy and the
    pixmaps inside it are shared, so handing the same object out is safe. The
    platform is part of the key rather than settled at import, so that a test
    can stand on either one.
    """
    shape = SHAPES.get(name)
    if shape is None:
        return QIcon()
    mask = sys.platform == "darwin"
    if (name, mask) in _cache:
        return _cache[(name, mask)]

    result = QIcon()
    for size in SIZES:
        result.addPixmap(_stencil(shape, size, DARK) if mask
                         else _outlined(shape, size))
    if mask:
        # The line that makes it a template image: macOS then owns the colour,
        # and the icon follows the menu bar into dark mode instead of staying
        # black. Nothing outside macOS reads it, and setting it there would only
        # promise a recolouring that never comes.
        result.setIsMask(True)
    _cache[(name, mask)] = result
    return result


# --- the application icon --------------------------------------------------
#
# The menu bar wants a flat stencil; the Finder, the Dock, an application menu
# and a task bar want a picture. Same microphone, on a ground of its own, and
# drawn here as well so that `install-mac.sh` has an .icns and `install.sh` a
# set of PNGs to install without a binary blob living in the repository.

# What iconutil expects to find in an .iconset: each of these at 1x and 2x.
APP_ICON_SIZES = (16, 32, 128, 256, 512)
# What an XDG icon theme is asked for: a menu wants 48, a task bar 22 or 24, a
# file dialog 16, and something scaling for a HiDPI panel wants the big ones.
HICOLOR_SIZES = (16, 22, 24, 32, 48, 64, 128, 256)
# What goes into the .ico: the Windows shell picks the nearest of these itself,
# and 256 is the one the large view in Explorer and the setup program read.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def app_pixmap(size):
    """The application icon at one size: a white microphone on a blue tile."""
    pixmap, painter = _canvas(size)
    try:
        unit = size / 22.0
        # macOS rounds and shadows the tile itself for some icon styles but not
        # for a plain .icns, so the shape is drawn: the squircle radius Apple
        # uses is close enough to 22% of the side.
        ground = QLinearGradient(0, 0, 0, size)
        ground.setColorAt(0.0, QColor(0x3B, 0x82, 0xF6))
        ground.setColorAt(1.0, QColor(0x1D, 0x4E, 0xD8))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ground)
        inset = 1.0 * unit
        painter.drawRoundedRect(
            QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
            4.4 * unit, 4.4 * unit,
        )
        # The same glyph as the tray, in white and a little smaller so it sits
        # inside the tile rather than against its edges.
        painter.save()
        painter.translate(size / 2.0, size / 2.0)
        painter.scale(0.64, 0.64)
        painter.translate(-size / 2.0, -size / 2.0)
        _microphone(painter, size, LIGHT)
        painter.restore()
    finally:
        painter.end()
    return pixmap


_app_icon = None


def app_icon():
    """The application icon as a QIcon, for the windows and whatever lists them.

    Wayland reads it off the .desktop file instead, through the desktop file
    name the application sets, but X11 has only what the window itself carries.
    """
    global _app_icon
    if _app_icon is None:
        _app_icon = QIcon()
        for size in (16, 22, 24, 32, 48, 64, 128):
            _app_icon.addPixmap(app_pixmap(size))
    return _app_icon


def write_iconset(directory):
    """Write the PNGs `iconutil -c icns` reads. The directory it wrote to."""
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for size in APP_ICON_SIZES:
        for scale in (1, 2):
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            app_pixmap(size * scale).save(str(directory / name), "PNG")
    return directory


def write_hicolor(directory, name="dikte"):
    """Install the icon into an XDG theme. The paths it wrote.

    A .desktop file names its icon rather than carrying a path, and a name is
    only found if some installed theme has it. `audio-input-microphone`, which
    is what the entries used to name, is in Breeze and in Adwaita but not in
    hicolor, and hicolor is all Qt and a panel are left with on a session that
    names no desktop. Under a name of our own in hicolor it is found everywhere,
    since hicolor is the one theme every desktop is required to fall back to.
    """
    directory = pathlib.Path(directory)
    written = []
    for size in HICOLOR_SIZES:
        apps = directory / "hicolor" / f"{size}x{size}" / "apps"
        apps.mkdir(parents=True, exist_ok=True)
        path = apps / f"{name}.png"
        app_pixmap(size).save(str(path), "PNG")
        written.append(path)
    return written


def write_ico(path):
    """Write the Windows icon, every size in the one file. The path it wrote.

    An .ico is a directory of images and a run of image data after it, and
    since Vista each image may be a PNG rather than the bitmap-and-mask pair
    the format started with. PNGs are what Qt can already produce, so the
    twenty bytes of header per size are the whole of the work, and it saves
    both a build dependency and an icon file in the repository.
    """
    path = pathlib.Path(path)
    images = []
    for size in ICO_SIZES:
        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        app_pixmap(size).save(buffer, "PNG")
        images.append((size, bytes(buffer.data())))
        buffer.close()

    # 0, then 1 for an icon rather than a cursor, then the count.
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, data = b"", b""
    for size, png in images:
        # A side of 256 is written as 0: the field is one byte, and the format
        # spends it on the sizes below that rather than on the one above.
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                               1, 32, len(png), offset)
        offset += len(png)
        data += png
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + data)
    return path


def _main(argv):
    """`trayicon.py <path>.iconset` for install-mac.sh, `--hicolor <dir>` for
    install.sh, `--ico <path>` for the Windows build.

    A QGuiApplication has to exist before a QPixmap can, and offscreen because
    this runs from a shell script with no window to open.
    """
    flag = argv[1] if len(argv) == 3 else ""
    if flag not in ("--hicolor", "--ico") and len(argv) != 2:
        print("usage: trayicon.py <directory>.iconset\n"
              "       trayicon.py --hicolor <icon directory>\n"
              "       trayicon.py --ico <path>.ico", file=sys.stderr)
        return 2
    from PyQt6.QtGui import QGuiApplication
    QGuiApplication.setAttribute(
        Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
    app = QGuiApplication(["dikte-icon", "-platform", "offscreen"])
    try:
        if flag == "--hicolor":
            for path in write_hicolor(argv[2]):
                print(path)
        elif flag == "--ico":
            print(write_ico(argv[2]))
        else:
            print(write_iconset(argv[1]))
    finally:
        del app
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
