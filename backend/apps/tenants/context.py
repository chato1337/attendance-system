from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.tenants.models import Organization

_current_organization: ContextVar[Organization | None] = ContextVar(
    "current_organization",
    default=None,
)


def set_current_organization(organization: Organization | None) -> Token:
    return _current_organization.set(organization)


def reset_current_organization(token: Token) -> None:
    _current_organization.reset(token)


def get_current_organization() -> Organization | None:
    return _current_organization.get()
