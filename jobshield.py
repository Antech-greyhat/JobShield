"""Compatibility entry point; the implementation lives in the jobshield package."""

from jobshield.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
