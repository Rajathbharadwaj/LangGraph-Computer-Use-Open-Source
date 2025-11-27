"""
Clerk Webhook Handler
Automatically syncs users from Clerk to your database
"""

import os
from fastapi import APIRouter, Request, HTTPException, Header
from svix.webhooks import Webhook, WebhookVerificationError
from database.database import SessionLocal
from database.models import User
from datetime import datetime
import json

router = APIRouter()

CLERK_WEBHOOK_SECRET = os.getenv("CLERK_WEBHOOK_SECRET", "")


@router.post("/api/webhooks/clerk")
async def clerk_webhook_handler(
    request: Request,
    svix_id: str = Header(None, alias="svix-id"),
    svix_timestamp: str = Header(None, alias="svix-timestamp"),
    svix_signature: str = Header(None, alias="svix-signature"),
):
    """
    Handle Clerk webhooks for user events

    Events handled:
    - user.created: Create user in database
    - user.updated: Update user in database
    - user.deleted: Mark user as inactive
    """

    # Get the raw body
    body = await request.body()
    body_str = body.decode()

    # Verify webhook signature
    if CLERK_WEBHOOK_SECRET:
        try:
            wh = Webhook(CLERK_WEBHOOK_SECRET)
            payload = wh.verify(body_str, {
                "svix-id": svix_id,
                "svix-timestamp": svix_timestamp,
                "svix-signature": svix_signature,
            })
        except WebhookVerificationError as e:
            print(f"⚠️  Webhook verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
    else:
        # If no secret is set, parse the body directly (NOT RECOMMENDED FOR PRODUCTION)
        print("⚠️  WARNING: Webhook secret not set. Skipping signature verification.")
        payload = json.loads(body_str)

    event_type = payload.get("type")
    data = payload.get("data", {})

    print(f"📨 Received Clerk webhook: {event_type}")

    db = SessionLocal()
    try:
        if event_type == "user.created":
            await handle_user_created(db, data)
        elif event_type == "user.updated":
            await handle_user_updated(db, data)
        elif event_type == "user.deleted":
            await handle_user_deleted(db, data)
        else:
            print(f"ℹ️  Unhandled event type: {event_type}")

        return {"success": True, "event": event_type}

    except Exception as e:
        print(f"❌ Error handling webhook: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


async def handle_user_created(db, data):
    """
    Handle user.created event
    Create a new user in the database
    """
    user_id = data.get("id")

    # Extract email - Clerk stores emails in email_addresses array
    email_addresses = data.get("email_addresses", [])
    primary_email = None

    for email_obj in email_addresses:
        if email_obj.get("id") == data.get("primary_email_address_id"):
            primary_email = email_obj.get("email_address")
            break

    if not primary_email and email_addresses:
        primary_email = email_addresses[0].get("email_address")

    if not primary_email:
        print(f"⚠️  No email found for user {user_id}")
        primary_email = f"{user_id}@unknown.com"

    # Check if user already exists
    existing_user = db.query(User).filter(User.id == user_id).first()

    if existing_user:
        print(f"ℹ️  User {user_id} already exists, skipping creation")
        return

    # Create new user
    new_user = User(
        id=user_id,
        email=primary_email,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        plan="free",  # Default plan
        is_active=True
    )

    db.add(new_user)
    db.commit()

    print(f"✅ Created user: {user_id} ({primary_email})")


async def handle_user_updated(db, data):
    """
    Handle user.updated event
    Update user information in the database
    """
    user_id = data.get("id")

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        print(f"⚠️  User {user_id} not found, creating new user")
        await handle_user_created(db, data)
        return

    # Extract email
    email_addresses = data.get("email_addresses", [])
    primary_email = None

    for email_obj in email_addresses:
        if email_obj.get("id") == data.get("primary_email_address_id"):
            primary_email = email_obj.get("email_address")
            break

    if primary_email:
        user.email = primary_email

    user.updated_at = datetime.utcnow()

    db.commit()

    print(f"✅ Updated user: {user_id}")


async def handle_user_deleted(db, data):
    """
    Handle user.deleted event
    Mark user as inactive (soft delete)
    """
    user_id = data.get("id")

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        print(f"⚠️  User {user_id} not found")
        return

    # Soft delete - mark as inactive
    user.is_active = False
    user.updated_at = datetime.utcnow()

    db.commit()

    print(f"✅ Deactivated user: {user_id}")
