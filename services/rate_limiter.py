"""
Rate limiting service using Redis
"""
import os
from datetime import datetime, timedelta
from typing import Optional
import redis.asyncio as redis

class RateLimiter:
    """
    Redis-based rate limiter
    """
    
    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis = redis.from_url(redis_url, decode_responses=True)
        
        # Rate limits from environment
        self.hourly_limit = int(os.getenv("RATE_LIMIT_PER_HOUR", "100"))
        self.daily_limit = int(os.getenv("RATE_LIMIT_PER_DAY", "1000"))
    
    async def check_rate_limit(self, user_id: str, endpoint: str) -> tuple[bool, Optional[int]]:
        """
        Check if user has exceeded rate limit
        
        Args:
            user_id: User ID
            endpoint: API endpoint
            
        Returns:
            (is_allowed, retry_after_seconds)
        """
        now = datetime.utcnow()
        
        # Check hourly limit
        hour_key = f"ratelimit:hour:{user_id}:{endpoint}:{now.strftime('%Y%m%d%H')}"
        hour_count = await self.redis.get(hour_key)
        
        if hour_count and int(hour_count) >= self.hourly_limit:
            # Calculate retry after
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            retry_after = int((next_hour - now).total_seconds())
            return False, retry_after
        
        # Check daily limit
        day_key = f"ratelimit:day:{user_id}:{endpoint}:{now.strftime('%Y%m%d')}"
        day_count = await self.redis.get(day_key)
        
        if day_count and int(day_count) >= self.daily_limit:
            # Calculate retry after
            next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            retry_after = int((next_day - now).total_seconds())
            return False, retry_after
        
        # Increment counters
        pipe = self.redis.pipeline()
        pipe.incr(hour_key)
        pipe.expire(hour_key, 3600)  # 1 hour
        pipe.incr(day_key)
        pipe.expire(day_key, 86400)  # 1 day
        await pipe.execute()
        
        return True, None
    
    async def get_usage(self, user_id: str, endpoint: str) -> dict:
        """
        Get current usage for user
        
        Args:
            user_id: User ID
            endpoint: API endpoint
            
        Returns:
            Usage statistics
        """
        now = datetime.utcnow()
        
        hour_key = f"ratelimit:hour:{user_id}:{endpoint}:{now.strftime('%Y%m%d%H')}"
        day_key = f"ratelimit:day:{user_id}:{endpoint}:{now.strftime('%Y%m%d')}"
        
        hour_count = await self.redis.get(hour_key) or "0"
        day_count = await self.redis.get(day_key) or "0"
        
        return {
            "hourly": {
                "used": int(hour_count),
                "limit": self.hourly_limit,
                "remaining": max(0, self.hourly_limit - int(hour_count))
            },
            "daily": {
                "used": int(day_count),
                "limit": self.daily_limit,
                "remaining": max(0, self.daily_limit - int(day_count))
            }
        }


# Global instance
rate_limiter = RateLimiter()

