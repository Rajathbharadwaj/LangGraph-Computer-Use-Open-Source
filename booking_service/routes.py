"""
Booking Service Routes

Public endpoints for voice agent booking form.
No authentication required - prospects fill out form via SMS link.
"""

import secrets
import httpx
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import PendingBooking

from .templates import (
    get_booking_form_html,
    get_already_submitted_html,
    get_expired_html,
    get_not_found_html,
)


router = APIRouter(prefix="/booking", tags=["booking"])


# ============================================================================
# Pydantic Models
# ============================================================================

class CreateBookingRequest(BaseModel):
    """Request from voice-agent to create a pending booking."""
    call_session_id: str
    webhook_url: str
    phone_number: str
    proposed_datetime: datetime


class CreateBookingResponse(BaseModel):
    """Response with booking URL for SMS."""
    booking_id: str
    url: str
    expires_at: datetime


class BookingFormSubmission(BaseModel):
    """Form data from prospect."""
    name: str
    email: EmailStr
    company: Optional[str] = None
    datetime: str  # ISO format datetime string


# ============================================================================
# Helper Functions
# ============================================================================

def generate_booking_id() -> str:
    """Generate a short, URL-safe booking ID."""
    return secrets.token_urlsafe(6)[:8]  # 8 characters


async def notify_voice_agent(booking: PendingBooking):
    """Send webhook to voice-agent with booking details."""
    if not booking.webhook_url:
        print(f"[Booking] No webhook URL for booking {booking.id}")
        return

    payload = {
        "booking_id": booking.id,
        "call_session_id": booking.call_session_id,
        "contact_name": booking.contact_name,
        "contact_email": booking.contact_email,
        "company_name": booking.company_name,
        "meeting_datetime": booking.selected_datetime.isoformat() if booking.selected_datetime else None,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(booking.webhook_url, json=payload)
            if response.status_code == 200:
                print(f"[Booking] Webhook sent successfully for {booking.id}")
            else:
                print(f"[Booking] Webhook failed for {booking.id}: {response.status_code}")
    except Exception as e:
        print(f"[Booking] Webhook error for {booking.id}: {e}")


# ============================================================================
# API Endpoints (for voice-agent)
# ============================================================================

@router.post("/api/create", response_model=CreateBookingResponse)
async def create_pending_booking(
    request: CreateBookingRequest,
    db: Session = Depends(get_db),
):
    """
    Create a pending booking (called by voice-agent when sending SMS link).

    This is an internal API - should be called with API key in production.
    """
    booking_id = generate_booking_id()
    expires_at = datetime.utcnow() + timedelta(hours=1)

    booking = PendingBooking(
        id=booking_id,
        call_session_id=request.call_session_id,
        webhook_url=request.webhook_url,
        phone_number=request.phone_number,
        proposed_datetime=request.proposed_datetime,
        status="pending",
        expires_at=expires_at,
    )

    db.add(booking)
    db.commit()

    # Use the request host to build the URL
    base_url = "https://app.paralleluniverse.ai"
    booking_url = f"{base_url}/booking/{booking_id}"

    print(f"[Booking] Created pending booking {booking_id} for {request.phone_number}")

    return CreateBookingResponse(
        booking_id=booking_id,
        url=booking_url,
        expires_at=expires_at,
    )


# ============================================================================
# Public Form Endpoints (no auth required)
# ============================================================================

@router.get("/{booking_id}", response_class=HTMLResponse)
async def show_booking_form(
    booking_id: str,
    db: Session = Depends(get_db),
):
    """Display the booking form for a prospect to fill out."""
    booking = db.query(PendingBooking).filter(PendingBooking.id == booking_id).first()

    if not booking:
        return HTMLResponse(content=get_not_found_html(), status_code=404)

    # Check if already submitted
    if booking.status == "submitted":
        return HTMLResponse(content=get_already_submitted_html())

    # Check if expired
    if booking.expires_at and datetime.utcnow() > booking.expires_at:
        booking.status = "expired"
        db.commit()
        return HTMLResponse(content=get_expired_html())

    # Show the form
    return HTMLResponse(
        content=get_booking_form_html(
            booking_id=booking_id,
            proposed_datetime=booking.proposed_datetime,
            phone_number=booking.phone_number,
        )
    )


@router.post("/{booking_id}")
async def submit_booking(
    booking_id: str,
    submission: BookingFormSubmission,
    db: Session = Depends(get_db),
):
    """
    Process booking form submission.

    1. Update booking with contact details
    2. Send webhook to voice-agent
    3. Return success
    """
    booking = db.query(PendingBooking).filter(PendingBooking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status == "submitted":
        raise HTTPException(status_code=400, detail="Booking already submitted")

    if booking.expires_at and datetime.utcnow() > booking.expires_at:
        raise HTTPException(status_code=400, detail="Booking link has expired")

    # Parse the datetime
    try:
        selected_dt = datetime.fromisoformat(submission.datetime)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    # Update booking
    booking.contact_name = submission.name
    booking.contact_email = submission.email
    booking.company_name = submission.company
    booking.selected_datetime = selected_dt
    booking.status = "submitted"
    booking.submitted_at = datetime.utcnow()

    db.commit()

    print(f"[Booking] Form submitted for {booking_id}: {submission.name} ({submission.email})")

    # Send webhook to voice-agent (async, don't block response)
    await notify_voice_agent(booking)

    return {"status": "ok", "message": "Booking confirmed"}
