from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2, max_length=255)


class RegisterResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserSummary(BaseModel):
    id: str
    role: str
    full_name: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserSummary


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class PasswordResetRequestSchema(BaseModel):
    email: EmailStr


class PasswordResetConfirmSchema(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)
