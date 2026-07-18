"""``python -m owr.etl`` entry point — delegates to the ``etl`` CLI."""

from owr.etl.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
