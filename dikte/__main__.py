#!/usr/bin/env python3
"""What `python3 -m dikte` and the installed `dikte` command both run.

The file is also executed by path, because that is what a desktop shortcut and
the launcher in ~/.local/bin do: neither knows a working directory to be in.
Run that way there is no package around it, so the checkout has to be put on
the import path here, before the first line of the application is imported.
"""

import os
import sys

if not __package__:
    # realpath, because the launcher is a symlink into the checkout: what has to
    # end up on the path is the checkout, not ~/.local/bin. The directory this
    # file is in comes off the path in exchange, so that a module beside it is
    # only ever reachable as part of the package.
    here = os.path.dirname(os.path.realpath(__file__))
    sys.path[:] = [p for p in sys.path if os.path.realpath(p or ".") != here]
    sys.path.insert(0, os.path.dirname(here))

from dikte.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
