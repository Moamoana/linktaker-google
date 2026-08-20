#!/usr/bin/env python
"""Command-line entry point.

    python linktaker.py --input keyword1.txt --from 2026-08-08 --until 2026-08-16
                        --sort latest --output hasil.txt --max-pages 2

Everything lives in the `linktaker` package; this file just launches it so the
tool can be run as a plain script. `python -m linktaker` works too.
"""

import sys

from linktaker.cli import main

if __name__ == "__main__":
    sys.exit(main())
