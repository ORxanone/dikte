# PyInstaller's description of the build, shared by the AppImage, the disk
# image and the Windows setup. Run it through build-appimage.sh, build-dmg.sh
# or build-windows.ps1 rather than by hand: each of those has a few steps of
# its own on either side of this.
#
# A directory rather than a single file, on all three. Onefile unpacks itself
# into a temporary directory on every start, which for something a global
# shortcut is meant to bring up is a second of nothing happening, and for the
# AppImage it would be an unpacking inside an unpacking. The single file people
# download is the AppImage, the .dmg and the setup program; this only has to be
# tidy inside them.

import os
import pathlib
import re
import sys

ROOT = pathlib.Path(SPECPATH).parent            # noqa: F821  (PyInstaller's)

# Read rather than imported. Putting the checkout on sys.path to import dikte
# would put this directory there under the name `packaging`, which is a real
# library that PyInstaller itself uses, and a spec file is no place to find out
# whether that matters.
__version__ = re.search(r'^__version__ = "(.*)"$',
                        (ROOT / "dikte" / "__init__.py").read_text(),
                        re.M).group(1)

MACOS = sys.platform == "darwin"
WINDOWS = sys.platform == "win32"
BUNDLE_ID = "io.github.yusufipk.dikte"

# PyQt6's wheel is most of the build, and most of the wheel is modules nothing
# here imports: Qt ships a browser engine, three declarative UI stacks and a
# 3D renderer. Naming them keeps the download to something a person on a slow
# connection will actually finish. Only the four in dikte's imports are left.
UNUSED_QT = [
    "PyQt6." + name for name in (
        "Qt3DAnimation", "Qt3DCore", "Qt3DExtras", "Qt3DInput", "Qt3DLogic",
        "Qt3DRender", "QtBluetooth", "QtCharts", "QtDataVisualization",
        "QtDesigner", "QtHelp", "QtLocation", "QtMultimedia",
        "QtMultimediaWidgets", "QtNfc", "QtPdf", "QtPdfWidgets",
        "QtPositioning", "QtQml", "QtQuick", "QtQuick3D", "QtQuickWidgets",
        "QtRemoteObjects", "QtSensors", "QtSerialPort", "QtSpatialAudio",
        "QtSql", "QtTest", "QtTextToSpeech", "QtWebChannel", "QtWebEngineCore",
        "QtWebEngineQuick", "QtWebEngineWidgets", "QtWebSockets",
    )
]

analysis = Analysis(                            # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "dikte" / "icons" / "*.svg"), "dikte/icons")],
    hiddenimports=["PyQt6.QtNetwork"],
    # tkinter is the other GUI toolkit CPython ships and would be dead weight;
    # dikte's own tests have no business in a build at all.
    excludes=UNUSED_QT + ["tkinter", "tests"],
    noarchive=False,
)

# Qt's xcb platform plugin uses libxkbcommon in two halves: the core library
# and libxkbcommon-x11, which allocates keymap objects and hands them to the
# core half to use and free, so the two must come from the same build. The
# build machine has only the core half installed, which had PyInstaller
# bundling that one while the other kept coming from the user's system, and a
# 22.04-era core freeing what a current x11 half allocated is the startup
# crash of issue #57. Ship neither: any desktop that can show a window
# carries both, from one build.
if not (MACOS or WINDOWS):
    analysis.binaries = [entry for entry in analysis.binaries
                         if "libxkbcommon" not in entry[0]]

archive = PYZ(analysis.pure)                    # noqa: F821

executable = EXE(                               # noqa: F821
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Dikte" if MACOS or WINDOWS else "dikte",
    console=False,
    # Every platform uses whatever the machine is, because no build here is
    # cross-compiled: the workflow runs one job per architecture.
    target_arch=None,
    # Ad-hoc, and only on a Mac, where an arm64 binary that carries no
    # signature at all is refused by the kernel rather than merely warned
    # about. build-dmg.sh signs the finished bundle over the top of this.
    codesign_identity="-" if MACOS else None,
    # Windows keeps the icon inside the executable, and build-windows.ps1 draws
    # it from the same shapes the tray uses. A Mac reads the one BUNDLE names
    # below, and the AppImage installs PNGs into the icon theme instead.
    icon=os.environ.get("DIKTE_ICO") or None,
)

# The same program a second time, as a console application, and only on
# Windows. A windowed executable there is one the loader gives no console and
# no standard output at all, so `dikte doctor` started from a terminal would
# print nothing to it and answer nothing to a script. Everywhere else the one
# executable does both jobs: a terminal that started it keeps its output, and
# nothing opens a window nobody asked for.
#
# Named apart from the windowed one rather than `dikte` beside `Dikte`.
# Windows matches a filename without regard to its case, so those two are one
# file in one directory: whichever PyInstaller writes second is the only one
# installed, and a build made on a case-sensitive filesystem never sees it.
console_executable = EXE(                       # noqa: F821
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="dikte-cli",
    console=True,
    target_arch=None,
    icon=os.environ.get("DIKTE_ICO") or None,
) if WINDOWS else None

collection = COLLECT(                           # noqa: F821
    executable,
    *([console_executable] if WINDOWS else []),
    analysis.binaries,
    analysis.datas,
    name="dikte",
)

if MACOS:
    # LSUIElement is the line that makes this a menu bar application: no Dock
    # icon, no menu of its own, nothing in the app switcher. The usage strings
    # are not decoration either, they are what the permission dialogs read out,
    # and a bundle that asks for the microphone without one is killed rather
    # than asked about.
    app = BUNDLE(                               # noqa: F821
        collection,
        name="Dikte.app",
        icon=os.environ.get("DIKTE_ICNS") or None,
        bundle_identifier=BUNDLE_ID,
        version=__version__,
        info_plist={
            "CFBundleName": "Dikte",
            "CFBundleDisplayName": "Dikte",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSMinimumSystemVersion": "11.0",
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription":
                "Dikte records what you dictate so that it can be transcribed.",
            "NSAppleEventsUsageDescription":
                "Dikte puts the transcript on the clipboard and pastes it into "
                "the window you were typing in.",
        },
    )
