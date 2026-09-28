#!/usr/bin/env python3
"""Backward-compatible entry point for exporting STREAM correlation logs."""

from __future__ import annotations

import sys

from extract_correlation import main


if __name__ == "__main__":
    raise SystemExit(main(["stream", *sys.argv[1:]]))
