#!/usr/bin/env python3
"""Quick check if Jira API token has permissions."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import httpx
from base64 import b64encode

email = os.getenv("JIRA_EMAIL", "chandpa.ashish007@gmail.com")
api_token = os.getenv("JIRA_API_TOKEN")

if not api_token:
    print("❌ Set JIRA_API_TOKEN environment variable")
    sys.exit(1)

token = b64encode(f"{email}:{api_token}".encode()).decode()
headers = {
    "Authorization": f"Basic {token}",
    "Accept": "application/json",
}

print("Testing API token permissions...\n")

# Test 1: Get current user
print("1. Can I access my user profile?")
try:
    response = httpx.get("https://ashish-chandpa.atlassian.net/rest/api/3/myself", headers=headers, timeout=10)
    if response.status_code == 200:
        user = response.json()
        print(f"   ✅ Yes! Logged in as: {user.get('displayName')} ({user.get('emailAddress')})")
    else:
        print(f"   ❌ No! Status: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: List all accessible projects
print("\n2. What projects can I access?")
try:
    response = httpx.get("https://ashish-chandpa.atlassian.net/rest/api/3/project", headers=headers, timeout=10)
    if response.status_code == 200:
        projects = response.json()
        if projects:
            print(f"   ✅ Found {len(projects)} project(s):")
            for p in projects:
                print(f"      - {p.get('key')}: {p.get('name')} ({p.get('projectTypeKey')})")
        else:
            print("   ⚠️  No projects found")
            print("      This means your token has no project permissions")
    else:
        print(f"   ❌ Failed: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 60)
print("If you see 'No projects found', you need to:")
print("1. Generate a new API token")
print("2. Make sure it has 'Browse Projects' permission")
print("3. Add yourself to the project with 'Browse' permission")
print("=" * 60)
