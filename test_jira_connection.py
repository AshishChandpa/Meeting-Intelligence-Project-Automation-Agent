#!/usr/bin/env python3
"""Test Jira connectivity and functionality.

This script tests the Jira integration independently of the main application.
It verifies connection, Epic creation, Issue creation, and Sprint creation.

Usage:
    python test_jira_connection.py
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agent.jira import JiraClient
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_result(test_name: str, success: bool, message: str = ""):
    """Print test result with color-like formatting."""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"\n{status}: {test_name}")
    if message:
        print(f"  {message}")


def test_connection(client: JiraClient) -> bool:
    """Test Jira connection and project access."""
    print_section("TEST 1: Connection & Project Access")

    try:
        result = client.test_connection()
        print(f"\n✅ Connected successfully!")
        print(f"  Project Name: {result.get('name', 'N/A')}")
        print(f"  Project Key: {result.get('key', 'N/A')}")
        print(f"  Project Type: {result.get('projectTypeKey', 'N/A')}")
        print(f"  Project URL: {result.get('self', 'N/A')}")

        # Check if it's a Scrum project
        project_type = result.get('projectTypeKey', '')
        if project_type == 'software':
            print(f"  ⚠️  Note: Project type is 'software'. Check if Scrum or Kanban.")
        elif project_type == 'next-gen':
            print(f"  ⚠️  Note: Next-gen projects (team-managed) may not work")

        return True
    except Exception as e:
        print_result("Connection Test", False, str(e))
        return False


def test_epic_creation(client: JiraClient, project_key: str) -> bool:
    """Test Epic creation."""
    print_section("TEST 2: Epic Creation")

    test_epic_name = f"Test Epic - {os.urandom(4).hex()}"

    try:
        print(f"\nAttempting to create epic: '{test_epic_name}'")
        epic = client.create_epic(
            title=test_epic_name,
            description="This is a test epic created by the test script"
        )

        print(f"\n✅ Epic created successfully!")
        print(f"  Epic Key: {epic['key']}")
        print(f"  Epic ID: {epic['id']}")
        print(f"  Epic URL: {epic['url']}")
        print(f"\n  🔗 View your epic at: {epic['url']}")

        # Store for cleanup
        return epic['key']
    except Exception as e:
        print_result("Epic Creation", False, str(e))

        # Check for common errors
        error_str = str(e)
        if "customfield_10011" in error_str:
            print("\n  📋 DIAGNOSIS:")
            print("     - Epic Name field (customfield_10011) is not available")
            print("     - Your project may not have Epic issue type enabled")
            print("     - OR you're using a Kanban project")
            print("\n  💡 SOLUTION:")
            print("     1. Use a Scrum project instead")
            print("     2. Or enable Epic issue type in Project Settings → Issue Types")
        elif "Epic" in error_str and "issue type" in error_str.lower():
            print("\n  📋 DIAGNOSIS:")
            print("     - Epic issue type does not exist in your project")
            print("\n  💡 SOLUTION:")
            print("     - Create a Scrum project (not Kanban)")
            print("     - Or enable Epic issue type in Project Settings")

        return None


def test_issue_creation(client: JiraClient, project_key: str, epic_key: str = None) -> bool:
    """Test Issue creation."""
    print_section("TEST 3: Issue Creation")

    test_issue_title = f"Test Issue - {os.urandom(4).hex()}"

    try:
        print(f"\nAttempting to create issue: '{test_issue_title}'")
        if epic_key:
            print(f"  Linking to Epic: {epic_key}")

        issue = client.create_issue(
            title=test_issue_title,
            description="This is a test issue created by the test script",
            issue_type="Story",
            priority="Medium",
            story_points=3,
            epic_key=epic_key
        )

        print(f"\n✅ Issue created successfully!")
        print(f"  Issue Key: {issue['key']}")
        print(f"  Issue ID: {issue['id']}")
        print(f"  Issue URL: {issue['url']}")
        print(f"\n  🔗 View your issue at: {issue['url']}")

        return True
    except Exception as e:
        print_result("Issue Creation", False, str(e))

        # Check for common errors
        error_str = str(e)
        if "customfield_10016" in error_str or "story_points" in error_str:
            print("\n  📋 DIAGNOSIS:")
            print("     - Story Points field is not available")
            print("     - Your project is likely Kanban (not Scrum)")
            print("\n  💡 SOLUTION:")
            print("     - Use a Scrum project for full functionality")
        elif "customfield_10014" in error_str:
            print("\n  📋 DIAGNOSIS:")
            print("     - Epic Link field is not available")
            print("     - Epic functionality may not be enabled")
            print("\n  💡 SOLUTION:")
            print("     - Enable Epic Link field in Project Settings → Fields")

        return False


def test_board_and_sprint(client: JiraClient, project_key: str) -> bool:
    """Test Board and Sprint availability."""
    print_section("TEST 4: Board & Sprint Check")

    try:
        # Get board ID
        print(f"\nFetching board for project: {project_key}")
        board_id = client.get_board_id()

        if board_id:
            print(f"\n✅ Board found!")
            print(f"  Board ID: {board_id}")
            print(f"  Board URL: https://{client.domain}/secure/RapidBoard.jspa?rapidView={board_id}")
            print("\n  💡 Sprint creation should work (Scrum project)")
            return True
        else:
            print(f"\n⚠️  No board found")
            print("  This is expected for Kanban projects")
            print("  Sprint creation will NOT work")
            return False

    except Exception as e:
        print_result("Board/Sprint Check", False, str(e))
        print("\n  📋 DIAGNOSIS:")
        print("     - No Scrum board found for this project")
        print("     - Sprints require a Scrum board")
        print("\n  💡 SOLUTION:")
        print("     - Create a Scrum project (not Kanban)")
        return False


def main():
    """Run all Jira tests."""
    print_section("Jira Integration Test Suite")
    print("\nThis script tests your Jira configuration")
    print("Make sure you've set these environment variables:")
    print("  - JIRA_DOMAIN")
    print("  - JIRA_EMAIL")
    print("  - JIRA_API_TOKEN")
    print("  - JIRA_PROJECT_KEY")

    # Read credentials from environment
    domain = os.getenv("JIRA_DOMAIN")
    email = os.getenv("JIRA_EMAIL")
    api_token = os.getenv("JIRA_API_TOKEN")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    if not all([domain, email, api_token, project_key]):
        print("\n❌ Missing credentials!")
        print("\nPlease set the following environment variables:")
        print("  export JIRA_DOMAIN='your-domain.atlassian.net'")
        print("  export JIRA_EMAIL='your-email@example.com'")
        print("  export JIRA_API_TOKEN='your-api-token'")
        print("  export JIRA_PROJECT_KEY='YOUR_PROJECT_KEY'")
        print("\nGet your API token from: https://id.atlassian.com/manage-api-tokens")
        sys.exit(1)

    print(f"\nConfiguration:")
    print(f"  Domain: {domain}")
    print(f"  Email: {email}")
    print(f"  Project Key: {project_key}")

    # Create client
    try:
        client = JiraClient(
            domain=domain,
            email=email,
            api_token=api_token,
            project_key=project_key
        )
    except Exception as e:
        print(f"\n❌ Failed to create Jira client: {e}")
        sys.exit(1)

    # Run tests
    results = {}

    # Test 1: Connection
    results['connection'] = test_connection(client)
    if not results['connection']:
        print("\n❌ Cannot proceed without valid connection")
        sys.exit(1)

    # Test 2: Epic Creation
    epic_key = test_epic_creation(client, project_key)
    results['epic'] = epic_key is not None

    # Test 3: Issue Creation
    results['issue'] = test_issue_creation(client, project_key, epic_key)

    # Test 4: Board & Sprint
    results['sprint'] = test_board_and_sprint(client, project_key)

    # Summary
    print_section("TEST SUMMARY")
    print()
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name.upper()}")

    print()
    if all(results.values()):
        print("🎉 All tests passed! Your Jira setup is working correctly.")
        print("\nYou can now use the Jira integration in the application.")
    elif results['connection'] and results['issue']:
        print("⚠️  Partial success:")
        print("    - Connection: ✅")
        print("    - Issue creation: ✅")
        if not results['epic']:
            print("    - Epic creation: ❌ (May not work with Kanban)")
        if not results['sprint']:
            print("    - Sprints: ❌ (Scrum projects only)")
        print("\n💡 You can use the app, but Epics/Sprints may not work with Kanban.")
    else:
        print("❌ Some critical tests failed. Please check the errors above.")
        print("\n💡 RECOMMENDATION:")
        print("   Create a new Scrum project in Jira and update your config.")

    print("\n" + "=" * 80)
    print("Test complete!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
