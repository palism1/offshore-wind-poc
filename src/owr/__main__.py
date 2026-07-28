"""``python -m owr`` entry point — delegates to the simulator CLI."""

from owr.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
