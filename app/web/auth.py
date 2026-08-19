"""Clave opcional del panel (HTTP Basic). Vacía = abierto en local."""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings

_basic = HTTPBasic(auto_error=False)


def require_panel(
    credentials: HTTPBasicCredentials | None = Depends(_basic),
) -> None:
    settings = get_settings()
    password = (settings.panel_password or "").strip()
    if not password:
        return
    expected_user = (settings.panel_user or "hogar").encode()
    expected_pass = password.encode()
    given_user = (credentials.username if credentials else "").encode()
    given_pass = (credentials.password if credentials else "").encode()
    user_ok = secrets.compare_digest(given_user, expected_user)
    pass_ok = secrets.compare_digest(given_pass, expected_pass)
    if credentials is None or not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clave del panel requerida",
            headers={"WWW-Authenticate": 'Basic realm="Contabilizador"'},
        )
