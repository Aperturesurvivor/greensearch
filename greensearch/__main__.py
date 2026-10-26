"""Allow `python -m greensearch ...` as an entry point."""

import sys

from greensearch.cli import main

if __name__ == "__main__":
    sys.exit(main())
