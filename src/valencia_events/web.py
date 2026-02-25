"""FastAPI onboarding endpoints.

MVP auth is bearer-token sessions persisted in SQLite.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from .models import LoginSession, User
from .onboarding import OnboardingService
from .storage import EventStorage


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3)
    preferences_blob: str | None = None


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)


class PreferencesRequest(BaseModel):
    preferences_blob: str | None = None


class UserResponse(BaseModel):
    id: int
    email: str
    preferences: str | None
    is_active: bool

    @classmethod
    def from_user(cls, user: User) -> UserResponse:
        return cls(
            id=user.id,
            email=user.email,
            preferences=user.preferences,
            is_active=user.is_active,
        )


class SessionResponse(BaseModel):
    session_token: str
    user: UserResponse

    @classmethod
    def from_session(cls, session: LoginSession) -> SessionResponse:
        return cls(
            session_token=session.session_token,
            user=UserResponse.from_user(session.user),
        )


def create_app(storage: EventStorage | None = None) -> FastAPI:
    app = FastAPI(title="Valencia Events Onboarding API")
    app.state.storage = storage or EventStorage()
    app.state.onboarding = OnboardingService(app.state.storage)

    def get_onboarding_service() -> OnboardingService:
        return app.state.onboarding

    def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required",
            )
        prefix = "bearer "
        if not authorization.lower().startswith(prefix):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required",
            )
        token = authorization[len(prefix) :].strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required",
            )
        return token

    @app.post(
        "/onboarding/register",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def register(
        payload: RegisterRequest,
        onboarding: OnboardingService = Depends(get_onboarding_service),
    ) -> SessionResponse:
        try:
            session = onboarding.register(
                email=payload.email,
                preferences_blob=payload.preferences_blob,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        return SessionResponse.from_session(session)

    @app.post("/onboarding/login", response_model=SessionResponse)
    def login(
        payload: LoginRequest,
        onboarding: OnboardingService = Depends(get_onboarding_service),
    ) -> SessionResponse:
        try:
            session = onboarding.login(email=payload.email)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        return SessionResponse.from_session(session)

    @app.get("/onboarding/me", response_model=UserResponse)
    def me(
        session_token: str = Depends(get_bearer_token),
        onboarding: OnboardingService = Depends(get_onboarding_service),
    ) -> UserResponse:
        try:
            user = onboarding.get_current_user(session_token=session_token)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc
        return UserResponse.from_user(user)

    @app.patch("/onboarding/preferences", response_model=UserResponse)
    def update_preferences(
        payload: PreferencesRequest,
        session_token: str = Depends(get_bearer_token),
        onboarding: OnboardingService = Depends(get_onboarding_service),
    ) -> UserResponse:
        try:
            user = onboarding.save_preferences(
                session_token=session_token,
                preferences_blob=payload.preferences_blob,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc
        return UserResponse.from_user(user)

    return app


app = create_app()
