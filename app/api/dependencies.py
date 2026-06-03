"""FastAPI dependencies for accessing the application container."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.container import Container


def get_container(request: Request) -> Container:
    """Retrieve the DI container stored in `app.state`."""
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]
