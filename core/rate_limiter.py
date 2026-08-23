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

"""THis class is to track message timestamps per ip in a dict.
it automatically prunt old entried older than 60 seconds (1 minute), with limit is 10
In other words, rate limit is 10 messages / min"""

class InMemoryRateLimiter:
    def __init__ (
        self, 
        max_requests: int = 10,
        window_seconds: int = 60,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def check(self, ip: str):
        now = time.time()
        timestamps = self.requests[ip]

        #prune the timestamps that is older than 1 min
        valid_timestamps = [t for t in timestamps if now - t < self.window_seconds]
        self.requests[ip] = valid_timestamps

        #check if user exceeded limit
        if len(valid_timestamps) >= self.max_requests:
            #time left until oldest request expires
            oldest = valid_timestamps[0]
            retry_after = int(self.window_seconds - (now - oldest)) + 1
            return False, max(retry_after, 1)

        #record new request timestamps
        self.requests[ip].append(now)

        return True, 0

chat_limiter = InMemoryRateLimiter(max_requests= 10, window_seconds=60)


        


