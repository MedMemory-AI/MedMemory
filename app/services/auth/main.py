from __future__ import annotations
from typing import Optional
from prisma.models import Patient
from app.core.db import db, connect_db
from app.core.logger import logger
from app.services.auth.crypto import hash_password, verify_password
from app.services.auth.jwt import create_access_token


class AuthService:
    """Coordinated workflow provider driving data serialization and credential validation."""
    
    @staticmethod
    async def register_new_patient(full_name: str, email: str, raw_password: str) -> tuple[Patient, str]:
        """Orchestrates database write verification and returns a new Patient instance and JWT access token."""
        await connect_db()
        normalized_email = email.lower().strip()
        
        existing_patient = await db.patient.find_unique(where={"email": normalized_email})
        if existing_patient:
            raise ValueError("An account with this email address is already registered.")
            
        secured_password = hash_password(raw_password)
        
        new_patient = await db.patient.create(
            data={
                "fullName": full_name,
                "email": normalized_email,
                "password": secured_password
            }
        )
        
        token = create_access_token({"id": str(new_patient.id), "email": new_patient.email})
        return new_patient, token


    @staticmethod
    async def authenticate_patient(email: str, raw_password: str) -> tuple[Patient, str]:
        """Validates login credentials against PostgreSQL hashes and returns user details and JWT token."""
        await connect_db()
        normalized_email = email.lower().strip()
        
        patient = await db.patient.find_unique(where={"email": normalized_email})
        if not patient or not verify_password(raw_password, patient.password):
            raise ValueError("Invalid email or password credential matching configuration.")
            
        token = create_access_token({"id": str(patient.id), "email": patient.email})
        return patient, token


    @staticmethod
    async def get_patient_profile(patient_id: str) -> Patient:
        """Fetches the authenticated patient's profile from the database."""
        await connect_db()

        patient = await db.patient.find_unique(where={"id": patient_id})
        if not patient:
            raise ValueError("Patient profile not found.")

        return patient
