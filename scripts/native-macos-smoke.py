#!/usr/bin/env python3
"""Exercise installer-generated launchers on disposable macOS runners.

Does not run the installer, register login items, access audio, or grant TCC.
The Cocoa/IPC application is synthetic; launcher and IPC helpers are real.
"""
import json
import os
from pathlib import Path
import plistlib
import re
import site
import subprocess
import sys
import sysconfig
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=60, **kwargs)


def wait_json(path, process=None):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                # A newly created response may still be being written.
                time.sleep(.1)
                continue
        if process is not None and process.poll() is not None:
            raise AssertionError(f"Native process exited: {process.returncode}")
        time.sleep(.1)
    raise AssertionError(f"No native response: {path.name}")


def main():
    if sys.platform != 'darwin':
        raise SystemExit('This probe requires a real macOS runner')
    artifact = ROOT / 'native-macos-results'
    artifact.mkdir(exist_ok=True)
    source = (ROOT / 'scripts/install-mac.sh').read_text()
    helper = re.search(r'c_string_literal\(\) \{.*?\n\}', source, re.S).group()
    template = re.search(r'cat > "\$LAUNCHER_SRC" <<EOF\n.*?\nEOF', source, re.S).group()
    cv = sysconfig.get_config_var
    library = (Path(sys.base_prefix) / 'Python' if cv('PYTHONFRAMEWORK') else
               Path(cv('LIBDIR')) / cv('LDLIBRARY')).resolve()
    assert library.is_file() and library.suffix != '.a', library
    results = {'platform': subprocess.check_output(['sw_vers'], text=True),
               'architecture': os.uname().machine, 'python': sys.version}
    with tempfile.TemporaryDirectory(prefix='dikte-native-') as temp:
        # LaunchServices canonicalizes macOS's /var -> /private/var alias.
        root = Path(temp).resolve()
        hostile = root / "paths ' \" $(touch INJECTED) `touch INJECTED2` \\\n"
        hostile.mkdir()
        bundle = hostile / 'Dikte.app'
        executable = bundle / 'Contents/MacOS/Dikte'
        executable.parent.mkdir(parents=True)
        entry = hostile / 'entry.py'
        response = root / 'response.json'
        restarted = root / 'restarted.json'
        server_name = 'dikte-native-' + uuid.uuid4().hex
        # Paths are embedded as Python literals, never interpolated shell source.
        entry.write_text('import sys, json, os\n'
            + f'os.environ.update({dict(HOME=str(root / "home"), XDG_CONFIG_HOME=str(root / "home/config"), XDG_DATA_HOME=str(root / "home/data"), XDG_CACHE_HOME=str(root / "home/cache"), QT_QPA_PLATFORM="cocoa")!r})\n'
            + f'sys.path.insert(0, {str(ROOT)!r})\n'
            + 'from pathlib import Path\nfrom dikte import ipc\n'
            + f'output=Path({str(response)!r})\n'
            + f'restarted=Path({str(restarted)!r})\n'
            + f'name={server_name!r}\n'
            + f'screenshot={str(artifact / "cocoa-widget.png")!r}\n'
            + '''
payload = dict(argv=sys.argv[1:], executable=sys.executable, bundle=ipc.macos_bundle())
if any(mode in sys.argv for mode in ('serve', 'gui-probe', 'restarted')):
    from PyQt6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QVBoxLayout, QLabel
    from PyQt6.QtCore import QTimer
    from PyQt6.QtNetwork import QLocalServer
    from dikte.app import _present
    from dikte.trayicon import app_icon
    app = QApplication([])
    assert app.platformName() == 'cocoa', app.platformName()
    app.setQuitOnLastWindowClosed(False)
    widget = QWidget()
    widget.resize(360, 180)
    widget.setWindowTitle('Dikte isolated native smoke')
    layout = QVBoxLayout(widget)
    layout.addWidget(QLabel('Synthetic native Cocoa launcher / IPC check'))
    tray = QSystemTrayIcon(app_icon())
    tray.show()
    _present(widget)
    app.processEvents()
    assert widget.isVisible()
    widget.showMinimized()
    app.processEvents()
    _present(widget)
    app.processEvents()
    assert not widget.isMinimized()
    def capture():
        assert widget.grab().save(screenshot)
        payload.update(platform=app.platformName(), visible=widget.isVisible(),
                       exposed=widget.windowHandle().isExposed(),
                       screens=len(app.screens()), tray_available=QSystemTrayIcon.isSystemTrayAvailable(),
                       tray_api_visible=tray.isVisible(),
                       tray_geometry=[tray.geometry().x(), tray.geometry().y(),
                                      tray.geometry().width(), tray.geometry().height()])
        (restarted if 'restarted' in sys.argv else output).write_text(json.dumps(payload))
        if 'serve' not in sys.argv:
            app.quit()
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    assert server.listen(name), server.errorString()
    def connection():
        sock = server.nextPendingConnection()
        pending = bytearray()
        def read():
            pending.extend(bytes(sock.readAll()))
            if b'\\n' not in pending:
                return
            text=bytes(pending).decode().strip()
            try:
                data=json.loads(text)
            except json.JSONDecodeError:
                data={'cmd':text}
            sock.write((json.dumps(dict(ok=True, command=data['cmd'], bundle=ipc.macos_bundle()))+'\\n').encode())
            sock.flush()
            sock.waitForBytesWritten(1000)
            sock.disconnectFromServer()
            if data['cmd']=='restart':
                QTimer.singleShot(100, restart)
        sock.readyRead.connect(read)
    def restart():
        ipc.respawn(['restarted'])
        app.quit()
    server.newConnection.connect(connection)
    QTimer.singleShot(1000, capture)
    QTimer.singleShot(30000, app.quit)
    app.exec()
    tray.hide()
    server.close()
else:
    output.write_text(json.dumps(payload))
''')
        home = root / 'home'
        home.mkdir()
        env = dict(os.environ, PY=sys.executable, PY_HOME=sys.base_prefix,
                   PY_SITE=site.getsitepackages()[0], PY_LIBRARY=str(library),
                   ENTRY=str(entry), LAUNCHER_SRC=str(root / 'launcher.c'),
                   HOME=str(home), XDG_CONFIG_HOME=str(home / 'config'),
                   XDG_DATA_HOME=str(home / 'data'), XDG_CACHE_HOME=str(home / 'cache'),
                   QT_QPA_PLATFORM='cocoa')
        generate = helper + '\n' + '\n'.join(
            f'C_{name}="$(c_string_literal "${name}")"'
            for name in ('PY_HOME', 'PY_SITE', 'PY_LIBRARY', 'ENTRY')) + '\n' + template
        run(['bash', '-c', generate], env=env, cwd=root)
        run(['clang', '-x', 'c', str(root / 'launcher.c'), '-o', str(executable)])
        metadata = {'CFBundleIdentifier':'io.github.yusufipk.dikte',
                    'CFBundleExecutable':'Dikte', 'CFBundleName':'Dikte',
                    'CFBundlePackageType':'APPL', 'CFBundleVersion':'1',
                    'LSUIElement':True}
        plist = bundle / 'Contents/Info.plist'
        plist.write_bytes(plistlib.dumps(metadata))
        run(['codesign', '--force', '--sign', '-', '--identifier', metadata['CFBundleIdentifier'], str(bundle)])
        run(['codesign', '--verify', '--deep', '--strict', str(bundle)])
        for args in [['probe'], [str(entry), '--gui', 'probe']]:
            response.unlink(missing_ok=True)
            run([str(executable), *args], env=env, cwd=root)
            data = wait_json(response)
            assert data['argv'] == ['--gui', 'probe'], data
            assert data['bundle'] == str(bundle), data
            assert Path(data['executable']) == executable, data
        results['compiled_launcher_and_reexec'] = 'passed'
        # Actual malformed/on-disk identity checks, not patched file reads.
        for content in [b'<?xml', plistlib.dumps(dict(metadata, CFBundleIdentifier='org.python.python'))]:
            plist.write_bytes(content)
            response.unlink()
            run([str(executable), 'probe'], env=env, cwd=root)
            assert wait_json(response)['bundle'] is None
        plist.write_bytes(plistlib.dumps(metadata))
        run(['codesign', '--force', '--sign', '-', '--identifier', metadata['CFBundleIdentifier'], str(bundle)])
        run(['codesign', '--verify', '--deep', '--strict', str(bundle)])
        results['plist_identity_and_codesign'] = 'passed'
        response.unlink()
        # Native Cocoa plus real QLocalServer/QLocalSocket; no app controller/audio.
        process = subprocess.Popen(['/usr/bin/open', '-n', '-W', '-a', str(bundle),
                                    '--args', 'serve'], env=env, cwd=root)
        try:
            results['cocoa'] = wait_json(response, process)
            sys.path.insert(0, str(ROOT))
            from dikte import ipc
            ipc.SERVER_NAME = server_name
            status = ipc.send('status')
            assert status and status['ok'] and status['bundle'] == str(bundle), status
            result = ipc.send('restart')
            assert result and result['ok'], result
            data = wait_json(restarted)
            assert data['argv'] == ['--gui', 'restarted'] and data['bundle'] == str(bundle), data
            assert data['platform'] == 'cocoa' and data['visible'] and data['exposed'], data
            results['cocoa_after_launchservices_restart'] = data
            process.wait(timeout=10)
            assert process.returncode == 0
            results['native_ipc_and_launchservices_restart'] = 'passed'
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        assert not (root / 'INJECTED').exists()
        assert not (root / 'INJECTED2').exists()
        results['path_injection_sentinels'] = 'absent'
    (artifact / 'result.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
