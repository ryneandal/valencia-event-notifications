"""Passkey (WebAuthn) helper functions."""

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    options_to_json,
    base64url_to_bytes,
    generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    RegistrationCredential,
    AuthenticatorAttachment,
    AuthenticationCredential,
)

# For dev: localhost relies on "localhost" RP ID effectively.
# In production, RP_ID must match the domain (e.g., valencia-events.com)
RP_ID = "localhost"
RP_NAME = "Valencia Events"
ORIGIN = "http://localhost:8000"


def make_registration_options(user_email: str, user_id: int):
    """Generate options for creating a new passkey."""
    return generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=str(user_id).encode(),  # Must be bytes
        user_name=user_email,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            user_verification=UserVerificationRequirement.PREFERRED,
            resident_key=None,
        ),
    )


def verify_registration(response_json: str, challenge: bytes):
    """Verify the registration response from the client."""
    credential = RegistrationCredential.parse_raw(response_json)
    
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_origin=ORIGIN,
        expected_rp_id=RP_ID,
    )
    return verification


def make_authentication_options():
    """Generate options for signing in with a passkey."""
    return generate_authentication_options(
        rp_id=RP_ID,
        user_verification=UserVerificationRequirement.PREFERRED,
    )


def verify_authentication(response_json: str, challenge: bytes, credential_public_key: bytes, sign_count: int):
    """Verify the authentication response from the client."""
    credential = AuthenticationCredential.parse_raw(response_json)
    
    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=challenge,
        expected_origin=ORIGIN,
        expected_rp_id=RP_ID,
        credential_public_key=credential_public_key,
        credential_current_sign_count=sign_count,
    )
    return verification
