from fastapi import Request
import time 
from collections import defaultdict

def get_client_ip(request: Request):
    """This function is to get the user's ip address even when hosted on render"""
    #when deployed on render, the real client ip is x-forwared-for
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()

    #Localhost fallback(to test on loclhost)
    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"

"""Tracks message timestamps per device ID or IP in memory.
Enforces max 5 messages per 60 seconds with a 30-second cooldown penalty."""

class InMemoryRateLimiter:
    def __init__(
        self, 
        max_requests: int = 5,
        window_seconds: int = 60,
        cooldown_seconds: int = 30,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.requests = defaultdict(list)
        self.cooldowns = {}

    def check(self, key: str):
        now = time.time()

        # 1. Check if user is currently under an active cooldown penalty
        if key in self.cooldowns:
            cooldown_end = self.cooldowns[key]
            if now < cooldown_end:
                retry_after = int(cooldown_end - now) + 1
                return False, max(retry_after, 1)
            else:
                del self.cooldowns[key]

        # 2. Prune timestamps older than window_seconds
        timestamps = self.requests[key]
        valid_timestamps = [t for t in timestamps if now - t < self.window_seconds]
        self.requests[key] = valid_timestamps

        # 3. Check if user hit the rate limit
        if len(valid_timestamps) >= self.max_requests:
            # Place user in cooldown
            self.cooldowns[key] = now + self.cooldown_seconds
            return False, self.cooldown_seconds

        # 4. Allowed: record new request timestamp
        self.requests[key].append(now)
        return True, 0

chat_limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60, cooldown_seconds=30)


        


