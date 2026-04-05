from functools import wraps

from django.core.cache import cache
from django.http import HttpResponseForbidden


def ratelimit(key="ip", rate="5/h", block=True):
    """
    DIY rate limiter using Django's default cache backend.
    No external dependencies (Redis, Memcached) required.

    Args:
        key:   "ip" to rate-limit by client IP address.
        rate:  "<max_requests>/<period>" where period is
               h (hour), m (minute), or s (second).
        block: If True, return 403 when limit is exceeded.

    Usage:
        @ratelimit(key="ip", rate="5/h", block=True)
        def my_view(request):
            ...
    """
    max_requests, period_char = rate.split("/")
    max_requests = int(max_requests)
    period_seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[period_char]

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if key == "ip":
                # Respect X-Forwarded-For for proxied environments (Heroku)
                forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
                client_key = (
                    forwarded.split(",")[0].strip() if forwarded
                    else request.META.get("REMOTE_ADDR", "unknown")
                )
            else:
                client_key = "global"

            cache_key = f"ratelimit:{view_func.__name__}:{client_key}"

            # Get current request count (default 0)
            current = cache.get(cache_key, 0)

            if current >= max_requests:
                if block:
                    return HttpResponseForbidden(
                        "<h1>403 Forbidden</h1>"
                        "<p>Rate limit exceeded. Please try again later.</p>"
                    )

            # Increment counter; set expiry on first request
            if current == 0:
                cache.set(cache_key, 1, period_seconds)
            else:
                # Use try/except for cache backends that don't support incr
                try:
                    cache.incr(cache_key)
                except ValueError:
                    cache.set(cache_key, current + 1, period_seconds)

            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
