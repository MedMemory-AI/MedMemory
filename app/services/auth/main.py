from __future__ import annotations
from datetime import datetime, timezone
from prisma.models import Patient
from app.core.config import settings
from app.core.db import db, connect_db
from app.core.logger import logger
from app.services.auth.crypto import hash_password, verify_password
from app.services.auth.email import send_otp_email
from app.services.auth.jwt import create_access_token
from app.services.auth.otp import generate_otp_code, otp_expiry


class AuthService:
    """Coordinated workflow provider driving data serialization and credential validation."""

    @staticmethod
    async def _issue_and_send_otp(patient_id: str, email: str) -> None:
        """Generates a fresh OTP, persists its hash, and delivers the plaintext code by email."""
        otp_code = generate_otp_code()
        await db.patient.update(
            where={"id": patient_id},
            data={
                "isVerified": False,
                "otpHash": hash_password(otp_code),
                "otpExpiresAt": otp_expiry(settings.OTP_EXPIRE_MINUTES),
            }
        )
        await send_otp_email(email, otp_code)
        logger.info(f"[Auth Service] OTP issued for patient profile: {patient_id}")

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
                "password": secured_password,
                "isVerified": False,
            }
        )

        await AuthService._issue_and_send_otp(str(new_patient.id), new_patient.email)
        new_patient = await db.patient.find_unique(where={"id": new_patient.id})
        if not new_patient:
            raise ValueError("Patient profile not found.")
        
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

        await AuthService._issue_and_send_otp(str(patient.id), patient.email)
        patient = await db.patient.find_unique(where={"id": patient.id})
        if not patient:
            raise ValueError("Patient profile not found.")
            
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

    @staticmethod
    async def verify_patient_otp(patient_id: str, otp_code: str) -> Patient:
        """Validates a pending OTP and marks the patient email as verified."""
        await connect_db()

        patient = await db.patient.find_unique(where={"id": patient_id})
        if not patient:
            raise ValueError("Patient profile not found.")
        if not patient.otpHash or not patient.otpExpiresAt:
            raise ValueError("No active verification OTP is pending for this account.")

        expires_at = patient.otpExpiresAt
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            raise ValueError("The verification OTP has expired. Request a new code by logging in again.")
        if not verify_password(otp_code, patient.otpHash):
            raise ValueError("Invalid verification OTP.")

        verified_patient = await db.patient.update(
            where={"id": patient_id},
            data={
                "isVerified": True,
                "otpHash": None,
                "otpExpiresAt": None,
            }
        )
        logger.info(f"[Auth Service] Email verified for patient profile: {patient_id}")
        return verified_patient
