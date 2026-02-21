"""Authentication routes for Passkeys."""

import json
import logging
from base64 import urlsafe_b64encode
from typing import Annotated

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from webauthn import options_to_json, base64url_to_bytes

from .passkeys import (
    make_registration_options,
    verify_registration,
    make_authentication_options,
    verify_authentication,
)
from valencia_events.storage import EventStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/webauthn", tags=["passkeys"])


def get_storage():
    return EventStorage("events.db")


# --- Registration ---

@router.post("/register/options")
async def register_options(
    request: Request,
    storage: Annotated[EventStorage, Depends(get_storage)],
):
    """Step 1: Get registration options (challenge)."""
    user_session = request.session.get("user")
    if not user_session:
        raise HTTPException(status_code=401, detail="Must be logged in to register a passkey")

    email = user_session.get("email")
    user_data = storage.get_user_by_email(email)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
        
    options = make_registration_options(email, user_data["id"])
    
    # Store challenge as base64url string
    challenge_b64 = urlsafe_b64encode(options.challenge).decode("utf-8").rstrip("=")
    request.session["passkey_challenge"] = challenge_b64
    
    return JSONResponse(content=json.loads(options_to_json(options)))


@router.post("/register/verify")
async def register_verify(
    request: Request,
    storage: Annotated[EventStorage, Depends(get_storage)],
):
    """Step 2: Verify and save passkey."""
    user_session = request.session.get("user")
    if not user_session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    
    challenge_b64 = request.session.get("passkey_challenge")
    if not challenge_b64:
        raise HTTPException(status_code=400, detail="Challenge missing")
    
    try:
        challenge = base64url_to_bytes(challenge_b64)
        verification = verify_registration(body_str, challenge)
        
        email = user_session.get("email")
        user_data = storage.get_user_by_email(email)
        
        # Store as base64 strings
        cred_id_b64 = urlsafe_b64encode(verification.credential_id).decode("utf-8").rstrip("=")
        pub_key_b64 = urlsafe_b64encode(verification.credential_public_key).decode("utf-8").rstrip("=")
        
        storage.store_passkey(
            user_id=user_data["id"],
            credential_id=cred_id_b64,
            public_key=pub_key_b64,
            sign_count=verification.sign_count
        )
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Passkey registration failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# --- Login ---

@router.post("/login/options")
async def login_options(request: Request):
    """Step 1: Get login options."""
    options = make_authentication_options()
    
    challenge_b64 = urlsafe_b64encode(options.challenge).decode("utf-8").rstrip("=")
    request.session["passkey_challenge"] = challenge_b64
    
    return JSONResponse(content=json.loads(options_to_json(options)))


@router.post("/login/verify")
async def login_verify(
    request: Request,
    storage: Annotated[EventStorage, Depends(get_storage)],
):
    """Step 2: Verify login."""
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    data = json.loads(body_str)
    
    # Credential ID from client response
    credential_id_b64 = data.get("id")
    if not credential_id_b64:
        raise HTTPException(status_code=400, detail="Credential ID missing")

    # DB Lookup using base64 string
    passkey = storage.get_passkey_by_credential_id(credential_id_b64)
    if not passkey:
        raise HTTPException(status_code=400, detail="Unknown credential")

    challenge_b64 = request.session.get("passkey_challenge")
    if not challenge_b64:
        raise HTTPException(status_code=400, detail="Challenge missing")
    challenge = base64url_to_bytes(challenge_b64)

    try:
        public_key = base64url_to_bytes(passkey["public_key"])
        
        verification = verify_authentication(
            body_str, 
            challenge, 
            public_key, 
            passkey["sign_count"]
        )
        
        # Manual user fetch
        import sqlite3
        with storage._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM users WHERE id = ?", (passkey["user_id"],)).fetchone()
            if not row:
                raise HTTPException(status_code=500, detail="User missing")
            user = dict(row)

        request.session["user"] = {"email": user["email"], "id": user["id"], "name": "Passkey User"}
        
        # Update sign count
        with storage._get_connection() as conn:
            conn.execute(
                "UPDATE passkeys SET sign_count = ? WHERE id = ?", 
                (verification.new_sign_count, passkey["id"])
            )

        return {"status": "ok", "redirect": "/dashboard"}
        
    except Exception as e:
        logger.error(f"Passkey login failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
