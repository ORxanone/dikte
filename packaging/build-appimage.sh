#!/usr/bin/env bash
# The Linux download: one file, no dependencies of its own beyond the sound
# and clipboard programs that come with the desktop.
#
# Run from anywhere; it works in build/ at the top of the checkout and leaves
# the finished AppImage in dist/. The release workflow runs it on the oldest
# Ubuntu still supported, because the glibc a build is linked against is the
# oldest one it will run on, and nothing here depends on which Ubuntu that is.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/build"
APPDIR="$BUILD/AppDir"
OUT="$ROOT/dist"
ARCH="${ARCH:-$(uname -m)}"
export ARCH

VERSION="$(cd "$ROOT" && python3 -c 'import dikte; print(dikte.__version__)')"

rm -rf "$BUILD" "$OUT"
mkdir -p "$APPDIR/usr/bin" "$OUT"

# 1. The application -------------------------------------------------------
python3 -m PyInstaller "$ROOT/packaging/dikte.spec" \
  --distpath "$BUILD/dist" --workpath "$BUILD/work" --noconfirm --clean
cp -a "$BUILD/dist/dikte/." "$APPDIR/usr/bin/"

# 2. The icon --------------------------------------------------------------
# Drawn by the application itself, which is why there is no image file in the
# repository and no second place to change what Dikte looks like. Offscreen,
# since this runs with no display anywhere near it.
icons="$BUILD/icons"
QT_QPA_PLATFORM=offscreen PYTHONPATH="$ROOT" \
  python3 -m dikte.trayicon --hicolor "$icons"
mkdir -p "$APPDIR/usr/share/icons"
cp -a "$icons/hicolor" "$APPDIR/usr/share/icons/"
# At the top as well, under the name the desktop entry gives: that copy is what
# appimagetool reads, and what a desktop shows before the file is ever run.
cp "$icons/hicolor/256x256/apps/dikte.png" "$APPDIR/dikte.png"

# 3. What the runtime reads ------------------------------------------------
# AppRun is started from the mount point, which is a different path every run,
# so it has to find its own directory rather than be told one.
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/dikte" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Exec names the file rather than a path: a desktop that integrates the
# AppImage rewrites this line with wherever the user keeps it, and Dikte writes
# its own copy of this entry on first run, which is the one that matters.
cat > "$APPDIR/dikte.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Dikte
X-AppImage-Version=$VERSION
Comment=Voice dictation: record, transcribe, clean up, paste
Exec=dikte
Icon=dikte
Categories=Utility;AudioVideo;
Terminal=false
StartupNotify=false
EOF

# 4. The AppImage ----------------------------------------------------------
# appimagetool is itself an AppImage, and a container or a CI runner has no
# FUSE for it to mount itself with, so it is asked to unpack instead.
tool="$BUILD/appimagetool"
if [ ! -x "$tool" ]; then
  curl -fsSL -o "$tool" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
  chmod +x "$tool"
fi
"$tool" --appimage-extract-and-run "$APPDIR" "$OUT/Dikte-$VERSION-$ARCH.AppImage"

echo "dist/Dikte-$VERSION-$ARCH.AppImage"
