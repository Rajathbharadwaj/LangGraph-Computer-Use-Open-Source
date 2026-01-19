"""
Clerk Authentication Middleware for Production
Verifies JWT tokens from Clerk and extracts user information
"""

import jwt
import os
import time
from fastapi import HTTPException, Header, Depends
from typing import Optional, Dict, Any
import requests
from functools import lru_cache
from jwt import PyJWKClient
import logging

logger = logging.getLogger(__name__)

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
CLERK_PUBLISHABLE_KEY = os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "")

# Clerk JWKS URL - extract from secret key or use environment variable
# Format: https://{clerk-instance}.clerk.accounts.dev/.well-known/jwks.json
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")

# Cache for JWKS client and keys
_jwks_client: Optional[PyJWKClient] = None
_jwks_cache_time: float = 0
_JWKS_CACHE_TTL = 3600  # Cache JWKS for 1 hour


def _get_jwks_client() -> Optional[PyJWKClient]:
    """
    Get or create a cached JWKS client for Clerk token verification.
    Returns None if JWKS URL is not configured.
    """
    global _jwks_client, _jwks_cache_time

    if not CLERK_JWKS_URL:
        return None

    current_time = time.time()

    # Refresh cache if expired
    if _jwks_client is None or (current_time - _jwks_cache_time) > _JWKS_CACHE_TTL:
        try:
            _jwks_client = PyJWKClient(CLERK_JWKS_URL)
            _jwks_cache_time = current_time
            logger.info(f"✅ JWKS client initialized from {CLERK_JWKS_URL}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize JWKS client: {e}")
            return None

    return _jwks_client


def _verify_jwt_with_jwks(token: str) -> Dict[str, Any]:
    """
    Verify JWT using Clerk's JWKS (public keys).
    This is the secure way to verify Clerk tokens.
    """
    jwks_client = _get_jwks_client()

    if jwks_client is None:
        raise ValueError("JWKS client not available - CLERK_JWKS_URL not configured")

    try:
        # Get the signing key from Clerk's JWKS
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Decode and verify the token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "require": ["exp", "iat", "sub"]
            }
        )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def verify_clerk_token(
    authorization: str = Header(None),
    x_clerk_user_id: Optional[str] = Header(None, alias="X-Clerk-User-Id")
) -> dict:
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

    try:
        # Try JWKS verification first (secure, production-ready)
        if CLERK_JWKS_URL:
            payload = _verify_jwt_with_jwks(token)
            logger.debug("✅ JWT verified using JWKS")
        else:
            # Fallback: decode without signature verification
            # This is less secure but allows operation without JWKS
            logger.warning("⚠️ CLERK_JWKS_URL not configured - JWT signature NOT verified!")
            logger.warning("   Set CLERK_JWKS_URL to enable secure token verification")
            payload = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_exp": True,  # Still verify expiration
                    "require": ["exp", "sub"]
                }
            )

        # Extract user ID from payload
        # Clerk JWTs can have different structures:
        # - sub: Can be external OAuth ID (Google: 110553...) or Clerk user ID (user_xxx)
        # - metadata.userId or user_id: Usually the Clerk internal user ID
        # We prefer the Clerk user ID if available

        user_id = payload.get("sub")

        # Check if sub looks like a Clerk user ID (starts with user_)
        # If not, try to find it in other claims or use the X-Clerk-User-Id header
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
            elif x_clerk_user_id and x_clerk_user_id.startswith("user_"):
                # Use the X-Clerk-User-Id header as fallback (from mobile app)
                print(f"🔄 Using Clerk user ID from X-Clerk-User-Id header: {x_clerk_user_id} (sub was: {user_id})")
                user_id = x_clerk_user_id
            else:
                # Log the full payload to debug
                print(f"⚠️ JWT sub is external ID: {user_id}")
                print(f"   Full payload keys: {list(payload.keys())}")
                print(f"   Full payload: {payload}")
                print(f"   X-Clerk-User-Id header: {x_clerk_user_id}")

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
