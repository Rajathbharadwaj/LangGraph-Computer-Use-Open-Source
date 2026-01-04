"""
HTML Templates for Booking Form

Mobile-responsive form for prospects to confirm meeting details.
"""

from datetime import datetime


def get_booking_form_html(
    booking_id: str,
    proposed_datetime: datetime,
    phone_number: str = "",
) -> str:
    """Generate the booking form HTML."""

    # Format proposed datetime for display and input
    display_time = proposed_datetime.strftime("%A, %B %d at %I:%M %p") if proposed_datetime else "TBD"
    input_datetime = proposed_datetime.strftime("%Y-%m-%dT%H:%M") if proposed_datetime else ""

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Confirm Your Demo - Parallel Universe</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}

        .container {{
            background: white;
            border-radius: 16px;
            padding: 32px 24px;
            max-width: 400px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}

        .logo {{
            text-align: center;
            margin-bottom: 24px;
        }}

        .logo h1 {{
            font-size: 24px;
            color: #1a1a2e;
            font-weight: 700;
        }}

        .logo p {{
            color: #666;
            font-size: 14px;
            margin-top: 4px;
        }}

        .meeting-time {{
            background: #f0f4ff;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 24px;
            text-align: center;
        }}

        .meeting-time .label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .meeting-time .time {{
            font-size: 18px;
            color: #1a1a2e;
            font-weight: 600;
            margin-top: 4px;
        }}

        .form-group {{
            margin-bottom: 20px;
        }}

        .form-group label {{
            display: block;
            font-size: 14px;
            font-weight: 500;
            color: #333;
            margin-bottom: 8px;
        }}

        .form-group input {{
            width: 100%;
            padding: 14px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: border-color 0.2s, box-shadow 0.2s;
        }}

        .form-group input:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
        }}

        .form-group input::placeholder {{
            color: #999;
        }}

        .submit-btn {{
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .submit-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
        }}

        .submit-btn:active {{
            transform: translateY(0);
        }}

        .submit-btn:disabled {{
            opacity: 0.7;
            cursor: not-allowed;
            transform: none;
        }}

        .success-state {{
            display: none;
            text-align: center;
            padding: 20px;
        }}

        .success-state.show {{
            display: block;
        }}

        .success-icon {{
            width: 80px;
            height: 80px;
            background: #10b981;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
        }}

        .success-icon svg {{
            width: 40px;
            height: 40px;
            color: white;
        }}

        .success-state h2 {{
            color: #1a1a2e;
            font-size: 24px;
            margin-bottom: 8px;
        }}

        .success-state p {{
            color: #666;
            font-size: 14px;
        }}

        .form-state {{
            display: block;
        }}

        .form-state.hide {{
            display: none;
        }}

        .error-message {{
            background: #fee2e2;
            color: #dc2626;
            padding: 12px;
            border-radius: 8px;
            font-size: 14px;
            margin-bottom: 16px;
            display: none;
        }}

        .error-message.show {{
            display: block;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>Parallel Universe</h1>
            <p>Confirm Your Demo</p>
        </div>

        <div class="form-state" id="formState">
            <div class="meeting-time">
                <div class="label">Proposed Meeting Time</div>
                <div class="time">{display_time}</div>
            </div>

            <div class="error-message" id="errorMessage"></div>

            <form id="bookingForm">
                <div class="form-group">
                    <label for="name">Your Name</label>
                    <input type="text" id="name" name="name" placeholder="John Smith" required>
                </div>

                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" placeholder="john@company.com" required>
                </div>

                <div class="form-group">
                    <label for="company">Company Name</label>
                    <input type="text" id="company" name="company" placeholder="Acme Inc">
                </div>

                <div class="form-group">
                    <label for="datetime">Meeting Time</label>
                    <input type="datetime-local" id="datetime" name="datetime" value="{input_datetime}" required>
                </div>

                <button type="submit" class="submit-btn" id="submitBtn">
                    Confirm Booking
                </button>
            </form>
        </div>

        <div class="success-state" id="successState">
            <div class="success-icon">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
            </div>
            <h2>You're All Set!</h2>
            <p>Your demo is confirmed. You'll receive a calendar invite shortly.</p>
        </div>
    </div>

    <script>
        const form = document.getElementById('bookingForm');
        const submitBtn = document.getElementById('submitBtn');
        const formState = document.getElementById('formState');
        const successState = document.getElementById('successState');
        const errorMessage = document.getElementById('errorMessage');

        form.addEventListener('submit', async (e) => {{
            e.preventDefault();

            submitBtn.disabled = true;
            submitBtn.textContent = 'Confirming...';
            errorMessage.classList.remove('show');

            const formData = {{
                name: document.getElementById('name').value,
                email: document.getElementById('email').value,
                company: document.getElementById('company').value,
                datetime: document.getElementById('datetime').value
            }};

            try {{
                const response = await fetch('/booking/{booking_id}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify(formData)
                }});

                if (response.ok) {{
                    formState.classList.add('hide');
                    successState.classList.add('show');
                }} else {{
                    const data = await response.json();
                    throw new Error(data.detail || 'Something went wrong');
                }}
            }} catch (error) {{
                errorMessage.textContent = error.message;
                errorMessage.classList.add('show');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Confirm Booking';
            }}
        }});
    </script>
</body>
</html>'''


def get_already_submitted_html() -> str:
    """HTML for when booking was already submitted."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Booking Already Confirmed</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 16px;
            padding: 40px 24px;
            max-width: 400px;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .icon {
            width: 80px;
            height: 80px;
            background: #10b981;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
        }
        .icon svg {
            width: 40px;
            height: 40px;
            color: white;
        }
        h1 { color: #1a1a2e; margin-bottom: 8px; }
        p { color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
        </div>
        <h1>Already Confirmed</h1>
        <p>This booking has already been confirmed. Check your email for the calendar invite!</p>
    </div>
</body>
</html>'''


def get_expired_html() -> str:
    """HTML for when booking link has expired."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Link Expired</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 16px;
            padding: 40px 24px;
            max-width: 400px;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .icon {
            width: 80px;
            height: 80px;
            background: #f59e0b;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
        }
        .icon svg {
            width: 40px;
            height: 40px;
            color: white;
        }
        h1 { color: #1a1a2e; margin-bottom: 8px; }
        p { color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
        </div>
        <h1>Link Expired</h1>
        <p>This booking link has expired. Please contact us to reschedule your demo.</p>
    </div>
</body>
</html>'''


def get_not_found_html() -> str:
    """HTML for when booking is not found."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Booking Not Found</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 16px;
            padding: 40px 24px;
            max-width: 400px;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .icon {
            width: 80px;
            height: 80px;
            background: #ef4444;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
        }
        .icon svg {
            width: 40px;
            height: 40px;
            color: white;
        }
        h1 { color: #1a1a2e; margin-bottom: 8px; }
        p { color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
        </div>
        <h1>Booking Not Found</h1>
        <p>We couldn't find this booking. The link may be incorrect or the booking may have been removed.</p>
    </div>
</body>
</html>'''
