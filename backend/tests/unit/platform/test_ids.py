import time
import uuid

from stylesense.platform.ids import new_id


def test_ids_are_rfc_9562_version_7() -> None:
    value = new_id()

    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_ids_embed_the_current_millisecond() -> None:
    before = time.time_ns() // 1_000_000
    value = new_id()
    after = time.time_ns() // 1_000_000

    assert before <= value.int >> 80 <= after


def test_ids_are_unique_and_ordered_across_milliseconds() -> None:
    first = new_id()
    time.sleep(0.002)
    second = new_id()

    assert first < second
    assert len({new_id() for _ in range(10_000)}) == 10_000
