#!/usr/bin/env python3
"""Simple Jira test - creates a basic Task issue without any custom fields."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import httpx
from base64 import b64encode

# Your credentials
domain = "ashish-chandpa.atlassian.net"
email = "chandpa.ashish007@gmail.com"
api_token = "ATATT3xFfGF0-AifkIJuMv6aWY5rAtBXPA4mkANa9p-NYTGDRQpqbVaXpoMQb4rJRqbGYBJkvxOTy-qOYziCYt1-C1oHGBS3A742xNo5Hz0V50QbG9uxrliJOseVqeCmPrRAA0RUmHgRI8uSikjoPcgeKhifqWE9b7zvY6c7OXxhXW9wCqm4m48=B3487F83"

# Create auth
token = b64encode(f"{email}:{api_token}".encode()).decode()
headers = {
    "Authorization": f"Basic {token}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

print("=" * 80)
print("  SIMPLE JIRA TEST - Kanban Compatible")
print("=" * 80)

# Test: Create the simplest possible issue
print("\nCreating a simple Task issue in KAN project...")
print("-" * 80)

test_title = f"Test Task from Script - {os.urandom(4).hex()}"

# Minimal payload - no custom fields at all
payload = {
    "fields": {
        "project": {"key": "KAN"},
        "summary": test_title,
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "This is a test task created by a simple script"
                        }
                    ]
                }
            ]
        },
        "issuetype": {"name": "Task"},  # Simple Task type
    }
}

try:
    response = httpx.post(
        f"https://{domain}/rest/api/3/issue",
        headers=headers,
        json=payload,
        timeout=30
    )

    if response.status_code == 201:
        data = response.json()
        print(f"\n✅ SUCCESS!")
        print(f"  Issue Key: {data['key']}")
        print(f"  Issue ID: {data['id']}")
        print(f"  URL: https://{domain}/browse/{data['key']}")
        print(f"\n🔗 Click to view: https://{domain}/browse/{data['key']}")
        print("\n" + "=" * 80)
        print("✅ Basic Jira integration WORKS!")
        print("=" * 80)
    else:
        print(f"\n❌ Failed with status {response.status_code}")
        try:
            error = response.json()
            print(f"Error: {error}")
        except:
            print(f"Response: {response.text}")

except Exception as e:
    print(f"\n❌ Exception: {e}")

print("\n" + "=" * 80)
print("If this worked, we can modify the app to use this simple approach")
print("=" * 80 + "\n")
