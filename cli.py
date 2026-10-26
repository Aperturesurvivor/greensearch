"""Legacy entry point: `python cli.py ...` still works.

The canonical entry points are the installed `greensearch` command and
`python -m greensearch`. This file exists only so existing scripts and
docs that call `python cli.py` do not break; it runs the same code.
"""

import sys

from greensearch.cli import main

if __name__ == "__main__":
    sys.exit(main())
