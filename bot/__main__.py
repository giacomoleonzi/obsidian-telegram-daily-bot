#!/usr/bin/env python3
"""Allow ``python -m bot`` as the container entrypoint."""

from __future__ import annotations

from bot.app import main

if __name__ == "__main__":
    main()
