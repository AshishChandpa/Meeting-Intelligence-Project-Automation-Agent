#!/usr/bin/env python3
"""List all Jira projects to find the correct project key."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agent.jira import JiraClient

# Read credentials
domain = os.getenv("JIRA_DOMAIN", "ashish-chandpa.atlassian.net")
email = os.getenv("JIRA_EMAIL", "chandpa.ashish007@gmail.com")
api_token = os.getenv("JIRA_API_TOKEN")

if not api_token:
    print("❌ JIRA_API_TOKEN not set")
    sys.exit(1)

print("Fetching all Jira projects...\n")

# Create client with dummy project key
client = JiraClient(
    domain=domain,
    email=email,
    api_token=api_token,
    project_key="DUMMY"
)

try:
    # Get all projects
    result = client._request("GET", f"{client.base_url}/project")

    print(f"Found {len(result)} projects:\n")
    print(f"{'KEY':<15} {'NAME':<40} {'TYPE'}")
    print("-" * 80)

    for project in result:
        key = project.get('key', 'N/A')
        name = project.get('name', 'N/A')
        ptype = project.get('projectTypeKey', 'N/A')

        # Highlight Scrum projects
        marker = "🏟️  " if ptype == 'software' else "   "

        print(f"{marker}{key:<15} {name:<40} {ptype}")

    print("\n" + "=" * 80)
    print("💡 Look for projects of type 'software' with Scrum boards")
    print("   Use the KEY of your desired project")
    print("=" * 80)

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
