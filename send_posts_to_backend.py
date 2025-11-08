#!/usr/bin/env python3
"""Send scraped posts to backend for analysis"""

import requests

# Your scraped posts (paste the full JSON array here)
posts = []  # Will be filled from command line

# Read from stdin if available
import sys
import json

if not sys.stdin.isatty():
    posts = json.load(sys.stdin)
else:
    print("Paste your scraped posts JSON and press Ctrl+D:")
    posts = json.load(sys.stdin)

print(f"📤 Sending {len(posts)} posts to backend...")

response = requests.post('http://localhost:8765/test-posts', json=posts)

print(f"✅ Response: {response.status_code}")
print(response.json())


