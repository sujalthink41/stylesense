import io
import json
from collections.abc import Callable

import pytest

from stylesense.platform.logging import configure_logging

LogReader = Callable[[], list[dict[str, object]]]


@pytest.fixture
def json_logs() -> LogReader:
    """Route JSON logs into a private buffer and return a reader for records so far."""
    buffer = io.StringIO()
    configure_logging(level="INFO", json_logs=True, stream=buffer)

    def read() -> list[dict[str, object]]:
        return [json.loads(line) for line in buffer.getvalue().splitlines() if line]

    return read
