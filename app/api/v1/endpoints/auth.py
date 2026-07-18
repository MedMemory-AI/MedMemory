from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import get_current_patient_id
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    AuthSuccessResponse,
    AuthSuccessData,
    MeProfileResponse,
    MeProfileData,
)
from app.services.auth.main import AuthService
from app.core.logger import logger

router = APIRouter(prefix="/auth", tags=["Stateless JWT Authentication"])


@router.post("/register", response_model=AuthSuccessResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> AuthSuccessResponse:
    """Handles patient onboarding, hashes incoming passwords, and provisions an initial session access token."""
    try:
        patient, token = await AuthService.register_new_patient(
            full_name=payload.fullName,
            email=payload.email,
            raw_password=payload.password
        )
        
        logger.info(f"[Auth API] Created patient profile record: {patient.id}")
        return AuthSuccessResponse(
            message="Patient account registered successfully.",
            data=AuthSuccessData(
                id=str(patient.id),
                fullName=patient.fullName,
                email=patient.email,
                accessToken=token
            )
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(val_err))
    except Exception as exc:
        logger.error(f"[Auth API Exception] Registration failed: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server registration process error.")


@router.post("/login", response_model=AuthSuccessResponse, status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest) -> AuthSuccessResponse:
    """Verifies account credentials and produces a valid session JWT for client-side storage."""
    try:
        patient, token = await AuthService.authenticate_patient(
            email=payload.email,
            raw_password=payload.password
        )
        
        logger.info(f"[Auth API] Session generated successfully for profile: {patient.id}")
        return AuthSuccessResponse(
            message="Login successful.",
            data=AuthSuccessData(
                id=str(patient.id),
                fullName=patient.fullName,
                email=patient.email,
                accessToken=token
            )
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(val_err))


@router.get("/me", response_model=MeProfileResponse, status_code=status.HTTP_200_OK)
async def get_me(patient_id: str = Depends(get_current_patient_id)) -> MeProfileResponse:
    """Returns the authenticated patient's profile details from the current session token."""
    try:
        patient = await AuthService.get_patient_profile(patient_id=patient_id)

        logger.info(f"[Auth API] Retrieved profile for patient: {patient.id}")
        return MeProfileResponse(
            message="Profile retrieved successfully.",
            data=MeProfileData(
                id=str(patient.id),
                fullName=patient.fullName,
                email=patient.email,
            )
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(val_err))
    except Exception as exc:
        logger.error(f"[Auth API Exception] Profile retrieval failed: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server profile retrieval process error.")


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout() -> dict:
    """
    Stateless endpoint notice. 
    Informs the frontend to remove the local web storage token context (localStorage/sessionStorage).
    """
    return {
        "success": True, 
        "message": "Stateless acknowledgment: Client app should purge active token parameters."
    }
