"""Auth routes — FR-AUTH-1..5 (UC-01, UC-02). See docs/02-system-design/13-api-specification.md §2."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.application.services.auth_service import AuthService
from app.domain.entities.user import User
from app.interface.api.v1.dependencies import get_auth_service, get_current_user
from app.interface.schemas.auth_schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserSummary,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, auth_service: AuthService = Depends(get_auth_service)):
    user = auth_service.register(body.email, body.password, body.full_name)
    return RegisterResponse(id=str(user.id), email=user.email, full_name=user.full_name, role=user.role.value)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, auth_service: AuthService = Depends(get_auth_service)):
    tokens = auth_service.login(body.email, body.password)
    user = auth_service.user_repo.get_by_email(body.email)
    return TokenResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=UserSummary(id=str(user.id), role=user.role.value, full_name=user.full_name),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)):
    tokens = auth_service.refresh(body.refresh_token)
    # Recover the user for the response payload via the token we just re-issued.
    payload = auth_service.jwt_service.decode_access_token(tokens.access_token)
    user = auth_service.user_repo.get_by_id(UUID(payload["sub"]))
    return TokenResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=UserSummary(id=str(user.id), role=user.role.value, full_name=user.full_name),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: LogoutRequest, auth_service: AuthService = Depends(get_auth_service),
           current_user: User = Depends(get_current_user)):
    auth_service.logout(body.refresh_token)
    return None
