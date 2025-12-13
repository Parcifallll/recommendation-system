"""
Test script for the recommendation system
Run this after starting the service to verify everything works
"""

import asyncio
import httpx
from datetime import datetime


BASE_URL = "http://localhost:8001"


async def test_health():
    """Test health endpoint"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        print(f"✅ Health check: {response.json()}")


async def test_recommendations():
    """Test recommendations endpoint"""
    request_data = {
        "userId": "test_user_123",
        "limit": 5,
        "excludeAuthorPosts": True
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/recommendations/",
            json=request_data,
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Recommendations received: {data['totalCount']} posts")
            
            if data['recommendations']:
                print("\nSample recommendation:")
                rec = data['recommendations'][0]
                print(f"  - Post ID: {rec['id']}")
                print(f"  - Author: {rec['authorId']}")
                print(f"  - Text: {rec['text'][:100] if rec.get('text') else 'No text'}...")
                print(f"  - Likes: {rec['likesCount']}")
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")


async def test_refresh():
    """Test refresh endpoint"""
    user_id = "test_user_123"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/recommendations/refresh/{user_id}",
            timeout=30.0
        )
        
        if response.status_code == 200:
            print(f"✅ Recommendations refreshed: {response.json()}")
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")


async def main():
    """Run all tests"""
    print("🧪 Testing Recommendation Service\n")
    
    try:
        await test_health()
        print()
        
        await test_recommendations()
        print()
        
        await test_refresh()
        print()
        
        print("✅ All tests completed!")
        
    except httpx.ConnectError:
        print("❌ Could not connect to service. Make sure it's running on port 8001")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
