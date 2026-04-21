#!/usr/bin/env python3
"""Check what's stored in MongoDB."""

import os
import sys
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent / "src"))

load_dotenv()

uri = os.getenv("MONGODB_URI")
database = os.getenv("MONGODB_DATABASE", "meeting_intelligence")
collection = os.getenv("MONGODB_COLLECTION", "projects")

print("=" * 80)
print("  MongoDB Data Inspector")
print("=" * 80)

try:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db = client[database]

    print(f"\n📊 Database: {database}")
    print(f"📁 Collection: {collection}")

    # Check projects collection
    projects_col = db[collection]
    count = projects_col.count_documents({})

    print(f"\n📈 Projects in database: {count}")

    if count > 0:
        print(f"\n📋 Project List:")
        print("-" * 80)

        projects = projects_col.find({}, {
            "id": 1,
            "state.project_name": 1,
            "state.current_stage": 1,
            "state.stage4_approved": 1,
            "state.stage5_done": 1,
            "created_at": 1,
            "updated_at": 1
        })

        for proj in projects:
            project_id = proj.get("id", "N/A")[:8] + "..." if len(proj.get("id", "")) > 8 else proj.get("id", "N/A")
            name = proj.get("state", {}).get("project_name", "Unnamed")
            stage = proj.get("state", {}).get("current_stage", "unknown")
            stage4 = proj.get("state", {}).get("stage4_approved", False)
            stage5 = proj.get("state", {}).get("stage5_done", False)
            created = proj.get("created_at", "Unknown")

            print(f"\n  Project ID: {project_id}")
            print(f"  Name: {name}")
            print(f"  Stage: {stage}")
            print(f"  Stage 4 Approved: {stage4}")
            print(f"  Stage 5 Done: {stage5}")
            print(f"  Created: {created}")
            print("-" * 80)

    # Check checkpoints collection
    checkpoints_col = db[f"{collection}_checkpoints"]
    checkpoint_count = checkpoints_col.estimated_document_count()

    print(f"\n📈 Checkpoints in database: {checkpoint_count}")

    if checkpoint_count > 0:
        print(f"✅ Checkpoints are being saved (LangGraph state persistence)")

    # List all collections
    collections = db.list_collection_names()
    print(f"\n📁 All collections: {collections}")

    print("\n" + "=" * 80)
    if count == 0:
        print("⚠️  No projects found in database!")
        print("\nPossible reasons:")
        print("  1. Server was restarted with 'memory' backend")
        print("  2. Projects haven't been created yet with MongoDB backend")
        print("  3. Wrong database/collection name in .env")
    else:
        print(f"✅ Found {count} project(s) in MongoDB!")
    print("=" * 80 + "\n")

except Exception as e:
    print(f"\n❌ Error: {e}")
    sys.exit(1)
