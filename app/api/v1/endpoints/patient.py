from fastapi import APIRouter, HTTPException, status
from app.schemas.patient import PatientCreate, PatientResponse
from app.core.db import db
from typing import List

# Initialize specialized subdomain router paths
router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(payload: PatientCreate):
    # Check if a patient record with this unique email address is already present
    existing = await db.patient.find_unique(where={"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered!")
    
    # Dispatch write instructions to the data layer via the Prisma client...
    patient = await db.patient.create(
        data={
            "fullName": payload.fullName,
            "email": payload.email,
            "password": payload.password, # NOTE: In production, apply passlib/bcrypt hashing here!
        }
    )
    return patient


@router.get("/", response_model=List[PatientResponse], status_code=status.HTTP_200_OK)
async def get_all_patients():
    # Execute a bulk query fetch operation across the Patient collection table matrix
    patients = await db.patient.find_many()
    return patients
