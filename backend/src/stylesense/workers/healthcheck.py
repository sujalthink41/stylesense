"""Container healthcheck: exits 0 while the worker loop is alive (fresh heartbeat)."""

import sys

from stylesense.platform.config import get_settings
from stylesense.workers.heartbeat import FileHeartbeat

MAX_AGE_S = 90  # several missed poll cycles, not one slow batch


def main() -> int:
    fresh = FileHeartbeat(get_settings().worker_heartbeat_file).is_fresh(max_age_s=MAX_AGE_S)
    return 0 if fresh else 1


if __name__ == "__main__":
    sys.exit(main())
