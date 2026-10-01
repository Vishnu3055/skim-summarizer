from google.genai import errors

from utils import retry_with_backoff

calls = {"n": 0}


@retry_with_backoff(max_retries=3, base_delay=0.5)
def flaky():
    calls["n"] += 1
    if calls["n"] < 3:  # fail twice, then succeed
        raise errors.ClientError(429, {"error": {"message": "fake rate limit"}})
    return "success"


print(flaky())