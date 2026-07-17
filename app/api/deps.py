from fastapi import Request

def get_current_patient_id(request: Request) -> str:
    """
    Retrieves the verified patient ID injected by the AuthMiddleware.
    Guaranteed to exist on protected routes.
    """
    return request.state.patient_id
