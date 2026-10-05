"""Scores any request parser (rules or LLM) against the golden set."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from stylesense.modules.stylist.slots import Slots

GOLDEN_FILE = "understand_golden.jsonl"


@dataclass(frozen=True, slots=True)
class GoldenExample:
    text: str
    expect: dict[str, Any]


@dataclass(slots=True)
class Report:
    examples: int = 0
    fields: int = 0
    correct_fields: int = 0
    exact: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def field_accuracy(self) -> float:
        return self.correct_fields / self.fields if self.fields else 0.0

    @property
    def exact_match(self) -> float:
        return self.exact / self.examples if self.examples else 0.0


def load_golden() -> list[GoldenExample]:
    raw = (
        resources.files("stylesense.modules.stylist.evals").joinpath(GOLDEN_FILE).read_text("utf-8")
    )
    return [GoldenExample(**json.loads(line)) for line in raw.splitlines() if line.strip()]


def score(examples: list[GoldenExample], parse: Callable[[str], Slots]) -> Report:
    report = Report()
    for example in examples:
        _check(report, example, parse(example.text))
    return report


async def score_async(
    examples: list[GoldenExample], parse: Callable[[str], Awaitable[Slots]]
) -> Report:
    report = Report()
    for example in examples:
        _check(report, example, await parse(example.text))
    return report


def _check(report: Report, example: GoldenExample, got: Slots) -> None:
    report.examples += 1
    wrong = []
    for name, expected in example.expect.items():
        report.fields += 1
        actual = getattr(got, name)
        if actual == expected:
            report.correct_fields += 1
        else:
            wrong.append(f"{name}={actual!r} (expected {expected!r})")
    if wrong:
        report.failures.append(f"{example.text!r}: {', '.join(wrong)}")
    else:
        report.exact += 1
