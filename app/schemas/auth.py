# app/schemas/auth.py

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

class RegisterRequest(BaseModel):
    fullName: str = Field(..., min_length=2, max_length=100, description="Patient's full legal name")
    email: EmailStr = Field(..., description="Unique email address for login credentials")
    password: str = Field(..., min_length=8, max_length=100, description="Minimum 8-character password")

class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Credentials email")
    password: str = Field(..., description="Credentials password")

class TokenPayload(BaseModel):
    id: str = Field(..., description="Subject unique UUID context")
    email: str

class AuthSuccessData(BaseModel):
    id: str
    fullName: str
    email: str
    accessToken: str
    tokenType: str = "Bearer"

class AuthSuccessResponse(BaseModel):
    success: bool = True
    message: str
    data: AuthSuccessData


class MeProfileData(BaseModel):
    id: str
    fullName: str
    email: str


class MeProfileResponse(BaseModel):
    success: bool = True
    message: str
    data: MeProfileData
