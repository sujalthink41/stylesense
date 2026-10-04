from collections.abc import Sequence
from typing import Annotated

from fastapi import Depends, Request

from stylesense.bootstrap.container import Container
from stylesense.platform.config import Settings
from stylesense.platform.health import HealthCheck


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def get_settings(container: ContainerDep) -> Settings:
    return container.settings


def get_health_checks(container: ContainerDep) -> Sequence[HealthCheck]:
    return container.health_checks


SettingsDep = Annotated[Settings, Depends(get_settings)]
HealthChecksDep = Annotated[Sequence[HealthCheck], Depends(get_health_checks)]
