"""Backward-compatible entry point; install the package before use."""
from mergerisk.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
