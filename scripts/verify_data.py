#!/usr/bin/env python3
"""Check the public logs in a folder against the input catalogue (file name, size, SHA-256).

    python scripts/verify_data.py --data <folder with the public logs>

The work is done by ``wise.evaluation.data``.
"""

from wise.evaluation.data import main

if __name__ == "__main__":
    raise SystemExit(main())
