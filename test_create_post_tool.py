#!/usr/bin/env python3
"""
Test script for the create_post_via_extension tool
"""
import asyncio
import requests
from async_extension_tools import get_async_extension_tools

async def test_create_post():
    """Test creating a post via extension"""
    
    print("=" * 70)
    print("🧪 Testing create_post_via_extension tool")
    print("=" * 70)
    
    # Get extension tools
    tools = get_async_extension_tools()
    
    # Find the create_post tool
    create_post_tool = None
    for tool in tools:
        if tool.name == "create_post_via_extension":
            create_post_tool = tool
            break
    
    if not create_post_tool:
        print("❌ create_post_via_extension tool not found!")
        return
    
    print(f"✅ Found tool: {create_post_tool.name}")
    print(f"📝 Description: {create_post_tool.description[:100]}...")
    print()
    
    # Test post text
    test_post = "Testing the create_post tool! 🚀 This is automated via the Docker VNC extension."
    
    print(f"📤 Creating post: \"{test_post}\"")
    print(f"📏 Length: {len(test_post)} characters")
    print()
    
    try:
        # Call the tool
        result = await create_post_tool.ainvoke({"post_text": test_post})
        
        print("=" * 70)
        print("📊 RESULT:")
        print("=" * 70)
        print(result)
        print("=" * 70)
        
        if "✅" in result:
            print("\n🎉 SUCCESS! Post was created!")
            print("👀 Check the VNC viewer to see your post on X!")
        else:
            print("\n⚠️ Post creation may have failed. Check the error message above.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

async def test_backend_endpoint():
    """Test the backend endpoint directly"""
    
    print("\n" + "=" * 70)
    print("🧪 Testing backend endpoint directly")
    print("=" * 70)
    
    # Check if extension backend is running
    try:
        status_response = requests.get("http://localhost:8001/status", timeout=5)
        status_data = status_response.json()
        
        print(f"✅ Extension backend is running")
        print(f"📡 Connected users: {status_data.get('connected_users', [])}")
        
        # Find Docker extension user ID
        docker_user_id = None
        for user_id in status_data.get('connected_users', []):
            if user_id != "user_s2izyx2x2":  # Not the browser extension
                docker_user_id = user_id
                break
        
        if not docker_user_id:
            print("⚠️ No Docker extension found. Using default user_id.")
            docker_user_id = "default"
        else:
            print(f"🐳 Docker extension user ID: {docker_user_id}")
        
        print()
        
        # Test create-post endpoint
        test_post = "Direct backend test! 🎯 This should appear in the Docker VNC browser."
        
        print(f"📤 Sending POST request to /extension/create-post")
        print(f"📝 Post text: \"{test_post}\"")
        print()
        
        response = requests.post(
            "http://localhost:8001/extension/create-post",
            json={
                "post_text": test_post,
                "user_id": docker_user_id
            },
            timeout=20
        )
        
        result = response.json()
        
        print("=" * 70)
        print("📊 BACKEND RESPONSE:")
        print("=" * 70)
        print(result)
        print("=" * 70)
        
        if result.get("success"):
            print("\n🎉 SUCCESS! Backend endpoint works!")
        else:
            print("\n⚠️ Backend returned an error.")
            
    except requests.exceptions.ConnectionError:
        print("❌ Extension backend not running on port 8001")
        print("   Start it with: python backend_extension_server.py")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("\n🚀 Create Post Tool Test Suite\n")
    
    # Test 1: Backend endpoint
    asyncio.run(test_backend_endpoint())
    
    # Test 2: LangChain tool
    print("\n")
    asyncio.run(test_create_post())
    
    print("\n✅ Tests complete!")


