"""Runtime AI configuration (admin API + CLI): prices, task routing, usage, status."""

import uuid
from collections.abc import Callable, Collection
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import ColumnElement, Integer, case, cast, func, select
from sqlalchemy.dialects.postgresql import insert

from stylesense.ai.gateway.config import ConfigStore
from stylesense.ai.gateway.models import LlmModel, LlmTaskConfig, LlmUsage
from stylesense.ai.gateway.types import ModelRef
from stylesense.infra.database import UnitOfWork
from stylesense.platform.clock import Clock
from stylesense.platform.errors import AppError

_MICRO = Decimal(1_000_000)
UsdPerMtok = Field(ge=0, le=10_000, max_digits=12, decimal_places=6)


class InvalidAIConfigError(AppError):
    status_code = 422
    code = "invalid_ai_config"
    title = "AI configuration is invalid"


class ModelPriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["chat", "embedding"] = "chat"
    input_usd_per_mtok: Decimal = UsdPerMtok
    cached_input_usd_per_mtok: Decimal = UsdPerMtok
    output_usd_per_mtok: Decimal = UsdPerMtok
    active: bool = True


class ModelPriceOut(ModelPriceIn):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    model: str
    updated_at: datetime


class TaskConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: list[str] = Field(min_length=1, max_length=5)  # primary first, then fallbacks
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_input_tokens: int = Field(default=4_000, ge=100, le=200_000)
    max_output_tokens: int = Field(default=600, ge=16, le=32_000)
    timeout_s: float = Field(default=20, ge=1, le=120)
    cache_ttl_s: int = Field(default=0, ge=0, le=7 * 86_400)
    enabled: bool = True

    @field_validator("targets")
    @classmethod
    def _parse_targets(cls, targets: list[str]) -> list[str]:
        parsed = [str(ModelRef.parse(t.strip())) for t in targets]
        if len(set(parsed)) != len(parsed):
            raise ValueError("targets must not repeat")
        return parsed


class TaskConfigOut(TaskConfigIn):
    task: str
    updated_at: datetime


class UsageSummaryRow(BaseModel):
    day: date
    task: str
    provider: str
    model: str
    attempts: int
    ok: int
    errors: int
    invalid_outputs: int
    cache_hits: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    p95_latency_ms: int


class AIStatus(BaseModel):
    providers: list[str]
    embedding_model: str
    spent_today_usd: Decimal
    daily_budget_usd: Decimal


class LlmAdmin:
    def __init__(
        self,
        uow: Callable[[], UnitOfWork],
        *,
        config: ConfigStore,
        clock: Clock,
        known_providers: Collection[str],
    ) -> None:
        self._uow = uow
        self._config = config
        self._clock = clock
        self._known = frozenset(known_providers)

    async def list_models(self) -> list[ModelPriceOut]:
        async with self._uow() as uow:
            rows = (
                await uow.session.scalars(
                    select(LlmModel).order_by(LlmModel.provider, LlmModel.model)
                )
            ).all()
            return [ModelPriceOut.model_validate(r) for r in rows]

    async def upsert_model(
        self, ref: ModelRef, price: ModelPriceIn, *, actor: uuid.UUID | None
    ) -> ModelPriceOut:
        self._require_known(ref)
        values = {**price.model_dump(), "updated_by": actor, "updated_at": self._clock.now()}
        async with self._uow() as uow:
            row = (
                await uow.session.execute(
                    insert(LlmModel)
                    .values(provider=ref.provider, model=ref.model, **values)
                    .on_conflict_do_update(index_elements=["provider", "model"], set_=values)
                    .returning(LlmModel)
                )
            ).scalar_one()
            result = ModelPriceOut.model_validate(row)
        await self._config.invalidate()
        return result

    async def list_tasks(self) -> list[TaskConfigOut]:
        async with self._uow() as uow:
            rows = (
                await uow.session.scalars(select(LlmTaskConfig).order_by(LlmTaskConfig.task))
            ).all()
            return [_task_out(r) for r in rows]

    async def upsert_task(
        self, task: str, config: TaskConfigIn, *, actor: uuid.UUID | None
    ) -> TaskConfigOut:
        for target in config.targets:
            self._require_known(ModelRef.parse(target))
        values = {**config.model_dump(), "updated_by": actor, "updated_at": self._clock.now()}
        async with self._uow() as uow:
            row = (
                await uow.session.execute(
                    insert(LlmTaskConfig)
                    .values(task=task, **values)
                    .on_conflict_do_update(index_elements=["task"], set_=values)
                    .returning(LlmTaskConfig)
                )
            ).scalar_one()
            result = _task_out(row)
        await self._config.invalidate()  # every instance picks it up on its next call
        return result

    async def usage_summary(self, *, days: int) -> list[UsageSummaryRow]:
        since = self._clock.now() - timedelta(days=days)
        day = cast(func.date_trunc("day", LlmUsage.created_at), LlmUsage.created_at.type)

        def count(outcome: str) -> ColumnElement[Any]:
            return func.sum(case((LlmUsage.outcome == outcome, 1), else_=0))

        stmt = (
            select(
                day.label("day"),
                LlmUsage.task,
                LlmUsage.provider,
                LlmUsage.model,
                func.count().label("attempts"),
                count("ok").label("ok"),
                count("error").label("errors"),
                count("invalid_output").label("invalid_outputs"),
                count("cache_hit").label("cache_hits"),
                func.sum(LlmUsage.input_tokens).label("input_tokens"),
                func.sum(LlmUsage.output_tokens).label("output_tokens"),
                func.sum(LlmUsage.cost_micro_usd).label("cost"),
                cast(func.percentile_cont(0.95).within_group(LlmUsage.latency_ms), Integer).label(
                    "p95"
                ),
            )
            .where(LlmUsage.created_at >= since)
            .group_by(day, LlmUsage.task, LlmUsage.provider, LlmUsage.model)
            .order_by(day.desc(), func.sum(LlmUsage.cost_micro_usd).desc())
        )
        async with self._uow() as uow:
            rows = (await uow.session.execute(stmt)).all()
        return [
            UsageSummaryRow(
                day=r.day.date(),
                task=r.task,
                provider=r.provider,
                model=r.model,
                attempts=r.attempts,
                ok=r.ok,
                errors=r.errors,
                invalid_outputs=r.invalid_outputs,
                cache_hits=r.cache_hits,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                cost_usd=Decimal(r.cost) / _MICRO,
                p95_latency_ms=r.p95,
            )
            for r in rows
        ]

    def _require_known(self, ref: ModelRef) -> None:
        if ref.provider not in self._known:
            raise InvalidAIConfigError(
                f"unknown provider '{ref.provider}'; expected one of {sorted(self._known)}"
            )


def _task_out(row: LlmTaskConfig) -> TaskConfigOut:
    return TaskConfigOut(
        task=row.task,
        targets=list(row.targets),
        temperature=row.temperature,
        max_input_tokens=row.max_input_tokens,
        max_output_tokens=row.max_output_tokens,
        timeout_s=row.timeout_s,
        cache_ttl_s=row.cache_ttl_s,
        enabled=row.enabled,
        updated_at=row.updated_at,
    )
