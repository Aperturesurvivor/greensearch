"""Allow `python -m arboris ...` as an entry point."""

import sys

from arboris.cli import main

if __name__ == "__main__":
    sys.exit(main())
