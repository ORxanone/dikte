# Contributing

## Running the tests

```sh
python -m unittest discover          # all of them, about a second
python -m unittest tests.test_api    # one file
python -m unittest tests.test_api.Transcribe.test_no_key_at_all
```

Nothing to install: the tests use the standard library's `unittest`, and the
only dependency is the PyQt6 the application already needs. They reach neither
the network, the microphone, nor your real `~/.config/dikte`, so they are safe
to run anywhere and they run on a machine with no display.

CI runs the same command on Python 3.11 through 3.13. A pull request that turns
it red will not be merged.

## Writing one

Put it in `tests/`, named after the module it covers. Inherit from
`tests.support.DikteTest` whenever the code under test touches a file, a
setting or the interface language: it hands the test its own config and data
directories, resets the language, and puts them back afterwards.

`tests/support.py` has the rest of what you need:

| For | Use |
| --- | --- |
| An HTTP call | `fake_urlopen(reply, …)`, then read the recorded requests |
| A reply that fails | `http_error(429)`, `url_error()`, `raw_body("not json")` |
| Reading what was sent | `sent_json(request)`, `multipart_fields(request)` |
| A program on the PATH | `only_these_tools("pactl", "wl-copy")` |
| Standing on another system | `mock.patch.object(sys, "platform", "darwin")` |
| Audio | `silence()`, `tone()`, `speech()`, `stereo()`, `make_wav()` |
| A settings object | `self.config(cleanup_enabled=False)` |

Three things about this codebase trip up a new test:

**Signals from a worker thread are never delivered.** `Pipeline`, `MeetingPipeline`
and `FileTranscriber` emit from the thread `start()` spawned, which Qt queues
until an event loop runs one. Call `_work()` directly instead: it is the same
code one frame down, and the signals arrive at once.

**A level that never moves is not speech.** The silence check is relative, so a
steady tone reads as its own noise floor however loud it is. Use `speech()`
rather than `tone()` when a recording is meant to have somebody talking in it.

**`cli.launch_gui` replaces the process.** With no instance running, some verbs
`os.execv` into the application, which would take the test run with it. Patch
`cli.launch_gui`. `DikteTest` blocks `os.execv` as a backstop, so a test that
forgets fails rather than hangs.

## Another platform

Four systems are supported: Wayland, X11, macOS and Windows. Each one is a named
entry in a table, and one chooser picks between them, so a fifth adds an entry
and a line rather than a branch inside every function. The tables are
`paste.Desktop` (clipboard and key press), `audio.Sound` (capture, the device
lists, and whether the far side of a meeting can be recorded at all),
`paths.directories()` (where the settings and the data live) and `hotkey.backend()`,
which names the one mechanism a session has for holding a key. Keep `sys.platform`
inside the chooser and read it there every time: a constant settled at import is
one no test can stand somewhere else.

Where a platform cannot do something, say so in its table entry rather than in
the code that asks. `audio.Sound.meetings` is the shape of it: Windows offers no
capture device for what the speakers are playing, and a caller reading a False
there can tell that apart from an empty device list, which only means the tool
that lists them is not installed.

The tests are split along the same line, and almost none of them are skipped.
1096 of the 1159 run on any machine, including every line of the Wayland, X11,
macOS and Windows backends: the programs are faked at `shutil.which`, the
frameworks and system libraries at the one function that loads them
(`paste._win_api`, `hotkey._win_input`). A test class says which system it is
standing on rather than avoiding the question:

```python
class MacOS(ClipboardContract, DikteTest):
    platform = "darwin"
    here = paste.MACOS
```

so the Linux half is checked on a Mac, the macOS half on Linux and the Windows
half on both, and a change to a chooser cannot quietly break the platform nobody
is sitting at. What the systems owe in common is written once as a contract
class and subclassed by each of them.

The 43 that do carry `@linux_only` are the ones that would need the real thing:
the `/dev/input` listener, KDE's shortcut file, GNOME's gsettings. The 20 with
`@posix_only` are the half of `integrate.py` that writes files, the menu entry
and the login item a downloaded build puts down for itself, which want a home
directory laid out the way those two systems lay one out. Its Windows half is
one registry value, since the setup program there did the rest, and the three
functions that read and write it are faked like anything else. Mark a test
either way only when faking it would leave nothing to test. A test that quietly
stops running on the platform you are porting to protects nothing.

## What a pull request should carry

A change to behaviour comes with a test for it. Adding a provider means a row in
`config.TRANSCRIBERS` and a test that the request goes to the right URL with the
right fields; adding a platform means a test for whatever the parsing of its
device list, clipboard or shortcuts looks like. Adding a setting means both halves of `settings_ui.py`: the round
trip in `tests/test_ui.py` is what catches only one of them being written.

Match the surrounding code: it is plain Python with no framework, comments
explain why rather than what, and neither the code nor the commit messages use
an em dash.
