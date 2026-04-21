#!/usr/bin/env python3
"""Test MongoDB connection and help set it up."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pymongo import MongoClient
from dotenv import load_dotenv

# Load .env
load_dotenv()

uri = os.getenv("MONGODB_URI")
database = os.getenv("MONGODB_DATABASE", "meeting_intelligence")

print("=" * 80)
print("  MongoDB Connection Test")
print("=" * 80)

if not uri:
    print("\n❌ MONGODB_URI not found in .env file")
    print("\nPlease add:")
    print("  MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/")
    sys.exit(1)

print(f"\nTesting connection to:")
print(f"  URI: {uri[:30]}...")
print(f"  Database: {database}")

try:
    # Try to connect
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    result = client.admin.command('ping')

    print(f"\n✅ Connected successfully!")
    print(f"  MongoDB version: {result['ok']}")

    # List databases
    databases = client.list_database_names()
    print(f"\n📊 Available databases ({len(databases)}):")
    for db in sorted(databases):
        print(f"  - {db}")

    # Check if target database exists
    if database in databases:
        print(f"\n✅ Database '{database}' exists!")
        db = client[database]
        collections = db.list_collection_names()
        print(f"  Collections: {collections if collections else 'None yet'}")
    else:
        print(f"\n⚠️  Database '{database}' doesn't exist yet (will be created automatically)")

    print("\n" + "=" * 80)
    print("✅ MongoDB is working! You can now use:")
    print("   PROJECT_STORAGE_BACKEND=mongo")
    print("=" * 80 + "\n")

except Exception as e:
    print(f"\n❌ Connection failed!")
    print(f"  Error: {e}")
    print("\n" + "=" * 80)
    print("TROUBLESHOOTING:")
    print("=" * 80)
    print("""
1. Check if MongoDB Atlas cluster exists:
   - Go to: https://cloud.mongodb.com/
   - Check if your cluster is active (green status)

2. Check the connection string:
   - Click "Connect" → "Drivers" on your cluster
   - Copy the connection string
   - Format: mongodb+srv://<username>:<password>@<cluster>.mongodb.net/

3. Check IP whitelist:
   - Go to: Network Access → Add IP Address
   - Click "Allow Access from Anywhere" (0.0.0.0/0)

4. Check database user:
   - Go to: Database Access
   - Verify username/password are correct
   - Reset password if needed

5. ALTERNATIVE: Use local MongoDB:
   brew install mongodb-community
   brew services start mongodb-community
   MONGODB_URI=mongodb://localhost:27017
""")
    sys.exit(1)
