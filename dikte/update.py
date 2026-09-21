"""Whether a newer Dikte has been published, and where to get it.

GitHub is asked for the newest release, its number is held against the one this
build carries, and that is where it stops. Nothing is downloaded and nothing is
replaced. The four downloads are installed in four different ways, and three of
those belong to the platform rather than to Dikte: a Mac bundle is dragged into
Applications and cannot rewrite itself while it is running, the Windows setup
is an installer with an uninstall entry of its own, an AppImage is a single
file kept wherever its owner keeps it, and a checkout is updated with git. A
program that guessed at all four would be wrong on at least one of them, and
being wrong there means an installation somebody has to repair by hand. So the
answer ends in a browser, on the release page, where the same download that was
installed the first time is waiting.

The clock is kept in a file of its own rather than in the settings. A check
runs while the settings window may be open, and a background write into
config.json is exactly what would overwrite a setting somebody is in the middle
of changing.

Nothing here imports Qt or the rest of the application: `dikte update` at a
terminal and the timer behind the tray icon ask the same three questions of the
same module.
"""

import collections
import itertools
import json
import time

from . import __version__
from . import hub
from . import paths

REPO = "yusufipk/dikte"
# Where somebody is sent. GitHub redirects this to whatever the newest release
# is, so it stays right without anybody writing a number into it.
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

# Once a day. A release happens every few weeks at best, and a question nobody
# is waiting on is not one to ask GitHub on every start.
INTERVAL = 24 * 3600

# When the last check was, what it found, and which version has already been
# announced. In the data directory rather than the config one: it is not a
# setting, nobody edits it, and losing it costs one extra request.
STATE_FILE = paths.DATA_DIR / "update.json"

Release = collections.namedtuple("Release", "version url published")


def _numbers(version):
    """(1, 0, 2) for "v1.0.2", "1.0.2" and "1.0.2-dev.abc1234" alike.

    Empty for anything that does not start with a number, which is what a tag
    naming something other than a version comes back as.
    """
    number = str(version or "").strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = []
    for piece in number.split("."):
        digits = "".join(itertools.takewhile(str.isdigit, piece))
        if not digits:
            break
        parts.append(int(digits))
    return tuple((parts + [0, 0, 0])[:3]) if parts else ()


def newer(there, here=""):
    """Whether the release numbered `there` is one this build has not got.

    Only the numbers are compared, and what follows them is dropped. A build
    off master carries the released number with its commit after it
    (1.0.1-dev.abc1234), and that build is ahead of 1.0.1 rather than behind
    it; read as a version suffix it would be behind, and every nightly would be
    told to update to the release it was already past.
    """
    theirs = _numbers(there)
    return bool(theirs) and theirs > _numbers(here or __version__)


def state():
    """What the last check wrote down; empty when there has never been one."""
    try:
        stored = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}


def _store(**changes):
    stored = state()
    stored.update(changes)
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(stored), encoding="utf-8")
    except OSError:
        pass          # a check that cannot be written down still happened
    return stored


def due(now=0):
    """Whether a day has gone by since the last time anybody asked."""
    return (now or time.time()) - float(state().get("checked") or 0) >= INTERVAL


def latest(refresh=False):
    """The newest published release, asked for outright. Raises HubError."""
    tag, url, published = hub.newest_release(REPO, refresh=refresh)
    return Release(tag.lstrip("vV"), url or RELEASES_PAGE, published)


def remember(release):
    """Write down that a check has just happened, and what it found."""
    _store(checked=time.time(), version=release.version, url=release.url,
           published=release.published)


def pending():
    """The newer release the last check found, without asking anybody.

    What the tray icon is built from: the answer has to be there the moment it
    appears, and a request on the way to the screen is a request nobody has
    time for.
    """
    stored = state()
    version = stored.get("version") or ""
    if not newer(version):
        return None
    return Release(version, stored.get("url") or RELEASES_PAGE,
                   stored.get("published") or "")


def check(force=False):
    """A newer release, or None when there is nothing to say.

    The scheduled half: it asks only when a day has gone by, and answers from
    what the last check found in between. `force` is the button in Settings and
    the command line, which ask whatever the clock says.

    The clock here is the only throttle. Once it has decided to ask, it asks
    for real rather than reading hub.py's few hours of cache, which is there to
    keep a settings window from fetching the same model list twice in an
    evening and would only ever answer this with something it already knew.
    """
    if not force and not due():
        return pending()
    release = latest(refresh=True)
    remember(release)
    return release if newer(release.version) else None


def announced():
    """The version somebody has already been shown a notification about."""
    return state().get("announced") or ""


def mark_announced(version):
    """Said once. A daily check must not be a daily interruption."""
    _store(announced=version)
