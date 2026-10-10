"""Pydantic schemas for SecurePDF API contracts."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Request body for user registration."""

    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    """Public user representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: EmailStr
    is_active: bool

class TokenResponse(BaseModel):
    """JWT access token response."""
    access_token: str
    token_type: str

class LoginRequest(BaseModel):
    """Request body for user login."""
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)