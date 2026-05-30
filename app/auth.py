"""JWT verification + role-based access control.

Phase A.2 scaffolds a generic HS256 JWS verifier sharing
`NEXTAUTH_SECRET` with Studio. In Phase A.3 this will be upgraded to
decrypt NextAuth's JWE tokens directly so admins log in once via Studio
and the backend trusts the same session.

Token shape expected (matching Studio session payload):
    {
      "login": "octocat",                # GitHub username
      "role":  "viewer" | "editor" | "admin",
      "iat":   1700000000,
      "exp":   1700003600
    }
"""

from collections.abc import Iterable
from typing import Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import Settings, get_settings

Role = Literal["viewer", "editor", "admin"]

_security = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    login: str
    role: Role


def _decode(token: str, settings: Settings) -> dict:
    options = {"verify_aud": settings.jwt_audience is not None}
    return jwt.decode(
        token,
        settings.nextauth_secret,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        options=options,
    )


def _current_principal(
    credentials: HTTPAuthorizationCredentials | None,
    settings: Settings,
) -> Principal | None:
    if credentials is None:
        return None
    try:
        claims = _decode(credentials.credentials, settings)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    login = claims.get("login")
    role = claims.get("role")
    if not isinstance(login, str) or role not in ("viewer", "editor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims (login, role)",
        )
    return Principal(login=login, role=role)


def current_principal_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    settings: Settings = Depends(get_settings),
) -> Principal | None:
    """Returns the caller or None for anonymous requests."""
    return _current_principal(credentials, settings)


def require_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    settings: Settings = Depends(get_settings),
) -> Principal:
    principal = _current_principal(credentials, settings)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def require_role(*allowed: Role):
    """Dependency factory: enforce that the caller's role is in `allowed`."""
    allowed_set: set[Role] = set(allowed)

    def _dep(principal: Principal = Depends(require_principal)) -> Principal:
        if principal.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {sorted(allowed_set)}",
            )
        return principal

    return _dep


__all__: Iterable[str] = (
    "Principal",
    "Role",
    "current_principal_optional",
    "require_principal",
    "require_role",
)
