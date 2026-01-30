"""Authentication module using authlib."""

import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth

auth_router = APIRouter()

oauth = OAuth()

# Check if credentials are set (or mock/warn)

oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@auth_router.get("/login")
async def login(request: Request):
    """Initiate Google OAuth login."""
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@auth_router.get("/auth/callback")
async def auth_callback(request: Request):
    """Handle OAuth callback."""
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        return RedirectResponse(url="/?error=auth_failed")

    user_info = token.get("userinfo")
    if not user_info:
        user_info = token.get("userinfo") or token

    if user_info:
        request.session["user"] = dict(user_info)
        return RedirectResponse(url="/dashboard")
    
    return RedirectResponse(url="/?error=no_user_info")


@auth_router.get("/logout")
async def logout(request: Request):
    """Log out user."""
    request.session.pop("user", None)
    return RedirectResponse(url="/")
