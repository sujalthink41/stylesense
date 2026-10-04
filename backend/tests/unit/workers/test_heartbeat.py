import os
import time
from pathlib import Path

from stylesense.workers.heartbeat import FileHeartbeat


def test_beat_creates_and_refreshes_the_file(tmp_path: Path) -> None:
    heartbeat = FileHeartbeat(tmp_path / "hb")

    heartbeat.beat()

    assert heartbeat.is_fresh(max_age_s=5)


def test_stale_heartbeat_is_not_fresh(tmp_path: Path) -> None:
    path = tmp_path / "hb"
    heartbeat = FileHeartbeat(path)
    heartbeat.beat()
    old = time.time() - 120
    os.utime(path, (old, old))

    assert not heartbeat.is_fresh(max_age_s=60)


def test_missing_heartbeat_is_not_fresh(tmp_path: Path) -> None:
    assert not FileHeartbeat(tmp_path / "never-written").is_fresh(max_age_s=60)
