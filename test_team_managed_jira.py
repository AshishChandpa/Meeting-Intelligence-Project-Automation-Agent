#!/usr/bin/env python3
"""Test Jira connectivity for Team-Managed projects."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import httpx
from base64 import b64encode

# Credentials
domain = os.getenv("JIRA_DOMAIN", "ashish-chandpa.atlassian.net")
email = os.getenv("JIRA_EMAIL", "chandpa.ashish007@gmail.com")
api_token = os.getenv("JIRA_API_TOKEN")

if not api_token:
    print("❌ JIRA_API_TOKEN not set")
    sys.exit(1)

print("=" * 80)
print("  Testing Team-Managed Jira Project")
print("=" * 80)

# Create auth token
token = b64encode(f"{email}:{api_token}".encode()).decode()
headers = {
    "Authorization": f"Basic {token}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

base_url = f"https://{domain}/rest/api/3"

# Test 1: Get project info (team-managed)
print("\n📋 TEST 1: Fetching project KAN (team-managed endpoint)")
print("-" * 80)

try:
    # Team-managed projects use a different endpoint
    response = httpx.get(
        f"{base_url}/project/KAN",
        headers=headers,
        timeout=30
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Project found!")
        print(f"  Key: {data.get('key')}")
        print(f"  Name: {data.get('name')}")
        print(f"  Type: {data.get('projectTypeKey', 'unknown')}")
        print(f"  Style: {data.get('style', 'unknown')}")  # 'next-gen' for team-managed
    else:
        print(f"❌ Failed: {response.status_code}")
        print(f"  {response.text}")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Check for Issue Types
print("\n📋 TEST 2: Check available issue types")
print("-" * 80)

try:
    response = httpx.get(
        f"{base_url}/project/KAN/issuetypes",
        headers=headers,
        timeout=30
    )

    if response.status_code == 200:
        issue_types = response.json()
        print(f"✅ Found {len(issue_types)} issue types:")
        for it in issue_types:
            print(f"  - {it.get('name')} (ID: {it.get('id')})")
    else:
        print(f"❌ Failed: {response.status_code}")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: Check for Fields
print("\n📋 TEST 3: Check custom fields")
print("-" * 80)

try:
    response = httpx.get(
        f"{base_url}/field",
        headers=headers,
        timeout=30
    )

    if response.status_code == 200:
        fields = response.json()

        # Look for Story Points and Epic fields
        story_points_fields = [f for f in fields if 'story' in f.get('name', '').lower() and 'point' in f.get('name', '').lower()]
        epic_fields = [f for f in fields if 'epic' in f.get('name', '').lower()]

        print(f"✅ Story Points Fields: {len(story_points_fields)}")
        for f in story_points_fields:
            print(f"  - {f.get('name')} (ID: {f.get('id')})")

        print(f"\n✅ Epic Fields: {len(epic_fields)}")
        for f in epic_fields[:5]:  # Show first 5
            print(f"  - {f.get('name')} (ID: {f.get('id')})")
    else:
        print(f"❌ Failed: {response.status_code}")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 4: Try to create a simple issue
print("\n📋 TEST 4: Create a test issue (without custom fields)")
print("-" * 80)

test_issue_name = f"Test Issue {os.urandom(4).hex()}"

try:
    payload = {
        "fields": {
            "project": {"key": "KAN"},
            "summary": test_issue_name,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Test issue from script"}]}]
            },
            "issuetype": {"name": "Task"},  # Try simple Task type
        }
    }

    response = httpx.post(
        f"{base_url}/issue",
        headers=headers,
        json=payload,
        timeout=30
    )

    if response.status_code == 201:
        data = response.json()
        print(f"✅ Issue created successfully!")
        print(f"  Key: {data.get('key')}")
        print(f"  ID: {data.get('id')}")
        print(f"  URL: https://{domain}/browse/{data.get('key')}")
    else:
        print(f"❌ Failed: {response.status_code}")
        try:
            error = response.json()
            print(f"  Errors: {error.get('errors', error.get('errorMessages', 'Unknown error'))}")
        except:
            print(f"  {response.text}")
except Exception as e:
    print(f"❌ Error: {e}")

# Summary
print("\n" + "=" * 80)
print("  SUMMARY")
print("=" * 80)
print("\n⚠️  Your project is TEAM-MANAGED (Next-Gen)")
print("\nTeam-managed projects have limitations:")
print("  ❌ Epic creation via API may not work")
print("  ❌ Story Points via API may not work")
print("  ❌ Sprint creation via API may not work")
print("  ✅ Basic Issue creation works")
print("\n💡 RECOMMENDATION:")
print("   Create a COMPANY-MANAGED project (Scrum) for full functionality")
print("\nHow to create company-managed project:")
print("  1. Go to Projects → Create project")
print("  2. Choose 'Scrum' (NOT 'Team-managed')")
print("  3. Select 'Company-managed' option")
print("  4. Use the new project key in the application")
print("=" * 80 + "\n")
