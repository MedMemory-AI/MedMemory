from pydantic import BaseModel, EmailStr
from datetime import datetime


class PatientCreate(BaseModel):
    """
    Input Contract Validation: Enforces strict types when a client attempts 
    to create a new registration record.
    """
    fullName: str
    email: EmailStr
    password: str


class PatientResponse(BaseModel):
    id: str
    fullName: str
    email: EmailStr
    createdAt: datetime

    class Config:
        # Instructs Pydantic to read raw attributes directly off relational database object instances
        from_attributes = True
