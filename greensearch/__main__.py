"""Legacy ``python -m greensearch``: runs the Arboris CLI unchanged."""

from arboris.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
