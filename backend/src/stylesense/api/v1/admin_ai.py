from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from stylesense.ai.gateway.admin import (
    AIStatus,
    ModelPriceIn,
    ModelPriceOut,
    TaskConfigIn,
    TaskConfigOut,
    UsageSummaryRow,
)
from stylesense.ai.gateway.types import ModelRef
from stylesense.api.auth import Claims, require_role
from stylesense.api.dependencies import ContainerDep
from stylesense.api.rate_limit import rate_limited_user
from stylesense.modules.users.schemas import Role

router = APIRouter(
    prefix="/admin/ai",
    tags=["admin: ai"],
    dependencies=[Depends(require_role(Role.ADMIN)), Depends(rate_limited_user("api.per_user"))],
)

Slug = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9_.:-]{0,79}$")]
_MICRO = Decimal(1_000_000)


@router.get("/status", summary="Configured providers and today's spend against the budget")
async def ai_status(container: ContainerDep) -> AIStatus:
    settings = container.settings
    return AIStatus(
        providers=list(container.llm_providers),
        embedding_model=settings.embedding_model,
        spent_today_usd=Decimal(await container.gateway.budget.spent_today()) / _MICRO,
        daily_budget_usd=settings.llm_daily_budget_usd,
    )


@router.get("/models", summary="Model prices (a model can't be used without one)")
async def list_models(container: ContainerDep) -> list[ModelPriceOut]:
    return await container.llm_admin.list_models()


@router.put("/models/{provider}/{model}", summary="Create or update a model price")
async def put_model(
    provider: Slug, model: Slug, body: ModelPriceIn, claims: Claims, container: ContainerDep
) -> ModelPriceOut:
    return await container.llm_admin.upsert_model(
        ModelRef(provider, model), body, actor=claims.user_id
    )


@router.get("/tasks", summary="Task routing: primary model, fallbacks and limits")
async def list_tasks(container: ContainerDep) -> list[TaskConfigOut]:
    return await container.llm_admin.list_tasks()


@router.put("/tasks/{task}", summary="Create or update a task's routing (applies to all instances)")
async def put_task(
    task: Slug, body: TaskConfigIn, claims: Claims, container: ContainerDep
) -> TaskConfigOut:
    return await container.llm_admin.upsert_task(task, body, actor=claims.user_id)


@router.get("/usage", summary="Attempts, tokens, cost and p95 latency per day, task and model")
async def usage(
    container: ContainerDep, days: Annotated[int, Query(ge=1, le=90)] = 7
) -> list[UsageSummaryRow]:
    return await container.llm_admin.usage_summary(days=days)
