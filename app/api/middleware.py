import jwt
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.auth.jwt import decode_access_token


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Automated security middleware that intercepts requests targeting protected clinical routes
    and enforces stateless JWT authorization signatures before hitting route controllers.
    """
    def __init__(self, app, protected_prefixes: list[str] = None):
        super().__init__(app)
        # Define paths or prefixes that absolutely require valid authorization headers
        self.protected_prefixes = protected_prefixes or ["/ingestion", "/timeline"]


    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Determine if the current path requires security validation
        requires_auth = any(request.url.path.startswith(prefix) for prefix in self.protected_prefixes)
        
        if requires_auth:
            authorization: str = request.headers.get("Authorization")
            
            if not authorization:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"success": False, "detail": "Bearer token missing or invalid."}
                )
            
            try:
                # 2. Extract and validate Bearer schema token
                token_type, token = authorization.split(" ")
                if token_type.lower() != "bearer":
                    raise ValueError()
            except (ValueError, AttributeError):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"success": False, "detail": "Invalid Authorization header format. Must be 'Bearer <token>'"}
                )

            try:
                # 3. Decode signature and verify expiration bounds
                payload = decode_access_token(token)
                patient_id: str = payload.get("id")
                
                if not patient_id:
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"success": False, "detail": "Malformed token payload context."}
                    )
                
                # 4. Attach verified profile scope state onto request context safely
                request.state.patient_id = patient_id

            except jwt.ExpiredSignatureError:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"success": False, "detail": "Session expired. Please re-authenticate."}
                )
            except jwt.InvalidTokenError as err:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"success": False, "detail": f"Authentication failed: {str(err)}"}
                )

        # Proceed cleanly down the application routing chain
        response = await call_next(request)
        return response
