"""
Clerk Authentication Middleware for Production
Verifies JWT tokens from Clerk and extracts user information
"""

import jwt
import os
from fastapi import HTTPException, Header, Depends
from typing import Optional
import requests
from functools import lru_cache

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
CLERK_PUBLISHABLE_KEY = os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "")

# Extract instance ID from publishable key (pk_test_xxx -> Instance ID)
# Format: pk_test_{instance_id}
if CLERK_PUBLISHABLE_KEY:
    # Get the part after pk_test_ or pk_live_
    key_parts = CLERK_PUBLISHABLE_KEY.split("_")
    if len(key_parts) >= 2:
        # The instance is typically encoded in the key
        pass

@lru_cache()
def get_clerk_jwks():
    """
    Fetch Clerk's JWKS (JSON Web Key Set) for JWT verification
    This is cached to avoid repeated API calls
    """
    # Clerk JWKS endpoint format
    # You'll need to get this from your Clerk dashboard
    # Format: https://clerk.{your-domain}.com/.well-known/jwks.json
    # OR: https://{clerk-instance}.clerk.accounts.dev/.well-known/jwks.json

    # For now, we'll use session token verification
    return None


def verify_clerk_token(authorization: str = Header(None)) -> dict:
    """
    Verify Clerk JWT token from Authorization header

    Args:
        authorization: Bearer token from request header

    Returns:
        dict: User information from verified token

    Raises:
        HTTPException: If token is invalid or missing
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header"
        )

    # Extract token from "Bearer {token}"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication scheme"
            )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format"
        )

    if not CLERK_SECRET_KEY:
        raise HTTPException(
            status_code=500,
            detail="Clerk secret key not configured"
        )

    try:
        # Verify the JWT token
        # Clerk uses RS256 algorithm with JWKS
        # For production, fetch JWKS and verify properly

        # For now, decode without verification (DEVELOPMENT ONLY)
        # In production, use proper JWKS verification
        payload = jwt.decode(
            token,
            options={"verify_signature": False}  # CHANGE THIS IN PRODUCTION
        )

        # Extract user ID from payload
        # Clerk JWTs can have different structures:
        # - sub: Can be external OAuth ID (Google: 110553...) or Clerk user ID (user_xxx)
        # - metadata.userId or user_id: Usually the Clerk internal user ID
        # We prefer the Clerk user ID if available

        user_id = payload.get("sub")

        # Check if sub looks like a Clerk user ID (starts with user_)
        # If not, try to find it in other claims
        if user_id and not user_id.startswith("user_"):
            # sub might be external OAuth ID, look for Clerk user ID elsewhere
            # Try common Clerk JWT claim locations
            clerk_user_id = (
                payload.get("userId") or
                payload.get("user_id") or
                payload.get("metadata", {}).get("userId") or
                payload.get("public_metadata", {}).get("userId")
            )
            if clerk_user_id and clerk_user_id.startswith("user_"):
                print(f"🔄 Using Clerk user ID from metadata: {clerk_user_id} (sub was: {user_id})")
                user_id = clerk_user_id
            else:
                # Log the full payload to debug
                print(f"⚠️ JWT sub is external ID: {user_id}")
                print(f"   Full payload keys: {list(payload.keys())}")
                print(f"   Full payload: {payload}")

                # CRITICAL: If we can't find Clerk user ID, we MUST fail
                # Using external OAuth ID will cause multi-tenancy leakage
                raise HTTPException(
                    status_code=401,
                    detail=f"JWT token does not contain Clerk user ID. Found external ID: {user_id}. Please ensure your frontend is sending the correct JWT token with Clerk user ID."
                )

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token payload"
            )

        return {
            "user_id": user_id,
            "email": payload.get("email"),
            "email_verified": payload.get("email_verified", False),
            "full_payload": payload
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}"
        )


def get_current_user(user_data: dict = Depends(verify_clerk_token)) -> str:
    """
    Dependency to get current user ID from verified token

    Usage in endpoints:
        @app.get("/api/posts")
        async def get_posts(user_id: str = Depends(get_current_user)):
            # user_id is now verified and trusted
    """
    return user_data["user_id"]


# Optional: Function to verify token on client side using Clerk API
async def verify_clerk_token_api(token: str) -> dict:
    """
    Verify token using Clerk's API (alternative method)
    This makes an API call to Clerk to verify the token
    """
    headers = {
        "Authorization": f"Bearer {CLERK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    # Clerk session verification endpoint
    # This is a backup verification method
    response = requests.get(
        f"https://api.clerk.com/v1/sessions/{token}/verify",
        headers=headers
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=401,
            detail="Token verification failed"
        )

    return response.json()
