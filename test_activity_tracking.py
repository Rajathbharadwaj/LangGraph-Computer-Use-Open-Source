"""
Test Activity Tracking System

This script tests the activity tracking functionality:
1. Creates test activities in the Store
2. Retrieves them via the ActivityLogger
3. Tests the API endpoint
"""

import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


async def test_activity_logger():
    """Test ActivityLogger directly"""
    print("\n" + "="*80)
    print("TEST 1: ActivityLogger Direct Test")
    print("="*80)

    from langgraph.store.postgres import PostgresStore
    from activity_logger import ActivityLogger

    # Get database connection
    database_uri = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URI")
    if not database_uri:
        print("❌ DATABASE_URL not set")
        return False

    print(f"✅ Database URI: {database_uri[:50]}...")

    # Initialize Store
    try:
        store = PostgresStore(connection_string=database_uri)
        print("✅ PostgreSQL Store initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Store: {e}")
        return False

    # Create logger
    user_id = "test_activity_user"
    logger = ActivityLogger(store, user_id)
    print(f"✅ ActivityLogger created for user: {user_id}")

    # Test 1: Log a post
    print("\n📝 Logging test post...")
    logger.log_post(
        content="This is a test post about AI transforming software development!",
        status="success",
        post_url="https://x.com/test/status/123456789"
    )
    print("✅ Post logged")

    # Test 2: Log a comment
    print("\n💬 Logging test comment...")
    logger.log_comment(
        target="@elonmusk",
        content="Great insights on AI! 🚀",
        status="success"
    )
    print("✅ Comment logged")

    # Test 3: Log a failed action
    print("\n❌ Logging failed action...")
    logger.log_like(
        target="@sama's post",
        status="failed",
        error="Rate limit exceeded"
    )
    print("✅ Failed action logged")

    # Test 4: Retrieve activities
    print("\n📊 Retrieving recent activities...")
    activities = logger.get_recent_activity(limit=10)
    print(f"✅ Retrieved {len(activities)} activities")

    if len(activities) > 0:
        print("\nRecent activities:")
        for i, activity in enumerate(activities[:5], 1):
            timestamp = datetime.fromisoformat(activity["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  {i}. [{timestamp}] {activity['action_type']} - {activity['status']}")
            if activity.get("target"):
                print(f"     Target: {activity['target']}")
            if activity['details']:
                details_preview = str(activity['details'])[:80]
                print(f"     Details: {details_preview}...")
    else:
        print("⚠️  No activities found")

    return len(activities) > 0


async def test_api_endpoint():
    """Test the API endpoint"""
    print("\n" + "="*80)
    print("TEST 2: API Endpoint Test")
    print("="*80)

    import aiohttp

    user_id = "test_activity_user"
    url = f"http://localhost:8000/api/activity/recent/{user_id}?limit=10"

    print(f"Testing endpoint: {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ API Response: success={data['success']}, count={data['count']}")

                    if data['success'] and data['count'] > 0:
                        print(f"\nFirst activity:")
                        activity = data['activities'][0]
                        print(f"  Action: {activity['action_type']}")
                        print(f"  Status: {activity['status']}")
                        print(f"  Timestamp: {activity['timestamp']}")
                        return True
                    else:
                        print("⚠️  API returned no activities")
                        return False
                else:
                    print(f"❌ API returned status {resp.status}")
                    return False

    except aiohttp.ClientConnectorError:
        print("❌ Could not connect to backend server")
        print("   Make sure backend_websocket_server.py is running on port 8000")
        return False
    except Exception as e:
        print(f"❌ API test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("ACTIVITY TRACKING SYSTEM TEST SUITE")
    print("="*80)

    results = {
        "ActivityLogger": False,
        "API Endpoint": False
    }

    # Test 1: ActivityLogger
    results["ActivityLogger"] = await test_activity_logger()
    await asyncio.sleep(1)

    # Test 2: API Endpoint
    results["API Endpoint"] = await test_api_endpoint()

    # Summary
    print("\n" + "="*80)
    print("TEST RESULTS SUMMARY")
    print("="*80)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20} {status}")

    all_passed = all(results.values())
    print("\n" + "="*80)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("\nThe activity tracking system is working correctly.")
        print("Activities are being logged to the Store and can be retrieved via API.")
    else:
        print("⚠️  Some tests failed - check the output above")
        if not results["API Endpoint"]:
            print("\n💡 Tip: Make sure backend_websocket_server.py is running:")
            print("   python backend_websocket_server.py")
    print("="*80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
