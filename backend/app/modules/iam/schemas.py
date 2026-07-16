from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.iam.models import MemberRole


class RegisterInput(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    email: EmailStr
    password: str
    tenant_id: int | None = None


class AuthOutput(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class TenantBrief(BaseModel):
    id: int
    name: str
    role: str


class MeOutput(BaseModel):
    user_id: int
    name: str
    email: str
    tenant_id: int
    tenant_name: str
    role: str
    tenants: list[TenantBrief]


class MemberCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: MemberRole


class MemberUpdate(BaseModel):
    role: MemberRole | None = None
    is_active: bool | None = None


class MemberOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class AuditOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    action: str
    resource_type: str
    resource_id: str | None
    payload: dict | None
    created_at: datetime