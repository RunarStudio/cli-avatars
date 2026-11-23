"""Write demo memory map records into a data directory (not imported at runtime).

    python tools/gen_memmap_demo.py <data-dir> [project]

Then start the app with ``CLI_AVATARS_DATA_DIR=<data-dir>`` to see the map
filled. Records go through ``memmap.store`` like the hook's: relative paths
and lengths only.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memmap import store  # noqa: E402
from memmap.demo import records  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    project = argv[1] if len(argv) > 1 else "cli-avatars"
    rows = records(time.time())
    store.append_records(argv[0], project, rows)
    print(f"wrote {len(rows)} records for {project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
