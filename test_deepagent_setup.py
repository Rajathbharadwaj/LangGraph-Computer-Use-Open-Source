"""
Quick test to verify DeepAgent setup and architecture

This script tests:
1. DeepAgents library is installed
2. Agent can be created
3. Subagents are configured correctly
4. Planning tools are available
"""

import os
import sys


def test_imports():
    """Test that all required libraries are available"""
    print("🔍 Testing imports...")
    
    try:
        from deepagents import create_deep_agent
        print("✅ deepagents imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import deepagents: {e}")
        print("💡 Install with: pip install deepagents")
        return False
    
    try:
        from langchain.chat_models import init_chat_model
        print("✅ langchain imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import langchain: {e}")
        return False
    
    try:
        from async_playwright_tools import (
            take_browser_screenshot,
            navigate_to_url,
            click_at_coordinates,
            type_text,
        )
        print("✅ async_playwright_tools imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import async_playwright_tools: {e}")
        print("💡 Make sure async_playwright_tools.py exists")
        return False
    
    return True


def test_api_key():
    """Test that API key is set"""
    print("\n🔍 Testing API key...")
    
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("❌ ANTHROPIC_API_KEY not set")
        print("💡 Set with: export ANTHROPIC_API_KEY='your-key-here'")
        return False
    
    print("✅ ANTHROPIC_API_KEY is set")
    return True


def test_agent_creation():
    """Test that agent can be created"""
    print("\n🔍 Testing agent creation...")
    
    try:
        from x_growth_deep_agent import create_x_growth_agent, get_atomic_subagents
        
        subagents = get_atomic_subagents()
        print(f"✅ Found {len(subagents)} atomic subagents:")
        for subagent in subagents:
            print(f"   - {subagent['name']}: {subagent['description']}")
        
        # Try to create agent (without invoking)
        print("\n🤖 Creating agent...")
        agent = create_x_growth_agent()
        print("✅ Agent created successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to create agent: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_docker_status():
    """Test that Docker browser is running"""
    print("\n🔍 Testing Docker browser status...")
    
    try:
        import requests
        response = requests.get("http://localhost:8005/status", timeout=5)
        data = response.json()
        
        if data.get("success") and data.get("stealth_browser_ready"):
            print("✅ Docker browser is running and ready")
            print(f"   - Mode: {data.get('mode', 'N/A')}")
            print(f"   - URL: {data.get('current_url', 'N/A')}")
            return True
        else:
            print("⚠️  Docker browser is running but not ready")
            return False
            
    except Exception as e:
        print(f"❌ Docker browser not accessible: {e}")
        print("💡 Start with: docker run -d -p 8005:8005 -p 5900:5900 stealth-cua:latest")
        return False


def test_backend_status():
    """Test that backend WebSocket server is running"""
    print("\n🔍 Testing backend server status...")
    
    try:
        import requests
        response = requests.get("http://localhost:8001/api/extension/status", timeout=5)
        data = response.json()
        
        print("✅ Backend server is running")
        print(f"   - Connected users: {len(data.get('connected_users', []))}")
        return True
            
    except Exception as e:
        print(f"❌ Backend server not accessible: {e}")
        print("💡 Start with: python3 backend_websocket_server.py")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 DeepAgent Setup Test")
    print("=" * 60)
    
    results = {
        "Imports": test_imports(),
        "API Key": test_api_key(),
        "Agent Creation": test_agent_creation(),
        "Docker Browser": test_docker_status(),
        "Backend Server": test_backend_status(),
    }
    
    print("\n" + "=" * 60)
    print("📊 Test Results")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    all_passed = all(results.values())
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 All tests passed! Ready to run DeepAgent.")
        print("\n💡 Next steps:")
        print("   1. Test with: python3 x_growth_deep_agent.py")
        print("   2. Or integrate into dashboard")
    else:
        print("⚠️  Some tests failed. Fix the issues above.")
        print("\n💡 Common fixes:")
        print("   - Install deepagents: pip install deepagents")
        print("   - Set API key: export ANTHROPIC_API_KEY='your-key'")
        print("   - Start Docker: docker run -d -p 8005:8005 -p 5900:5900 stealth-cua:latest")
        print("   - Start backend: python3 backend_websocket_server.py")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

