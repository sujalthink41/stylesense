import time
from pathlib import Path


class FileHeartbeat:
    """Touches a file after each healthy loop; the container healthcheck checks its age.

    A stuck event loop stops touching it, which a separate HTTP thread could never reveal.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def beat(self) -> None:
        self._path.touch()

    def is_fresh(self, *, max_age_s: float) -> bool:
        try:
            return time.time() - self._path.stat().st_mtime < max_age_s
        except FileNotFoundError:
            return False
