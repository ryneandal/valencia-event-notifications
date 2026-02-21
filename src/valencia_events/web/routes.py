"""Web application routes."""

import os
from typing import Annotated

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from valencia_events.storage import EventStorage

router = APIRouter()

BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


def get_storage():
    """Dependency for storage."""
    return EventStorage("events.db")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Landing page."""
    user = request.session.get("user")
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, storage: Annotated[EventStorage, Depends(get_storage)]):
    """User dashboard."""
    user_session = request.session.get("user")
    if not user_session:
        return RedirectResponse(url="/")

    email = user_session.get("email")
    user_data = storage.get_user_by_email(email)
    
    preferences = user_data["preferences"] if user_data else ""
    is_active = user_data["is_active"] if user_data and "is_active" in user_data else True
    
    passkeys = storage.get_passkeys_by_user(user_data["id"]) if user_data else []

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user_session,
            "preferences": preferences,
            "is_active": is_active,
            "passkeys": passkeys,
        },
    )


@router.post("/dashboard", response_class=HTMLResponse)
async def update_preferences(
    request: Request,
    storage: Annotated[EventStorage, Depends(get_storage)],
    preferences: Annotated[str, Form()] = "",
    is_active: Annotated[bool, Form()] = False,
    action: Annotated[str, Form()] = "save",
):
    """Update user preferences."""
    user_session = request.session.get("user")
    if not user_session:
        return RedirectResponse(url="/")

    form_data = await request.form()
    is_active_val = form_data.get("is_active") == "on"

    email = user_session.get("email")
    
    storage.update_user_preferences(email, preferences, is_active_val)

    return RedirectResponse(url="/dashboard", status_code=303)
