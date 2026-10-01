import functools
import logging
import random
import time

import httpx
from google.genai import errors


def setup_logging(log_file: str = "app.log") -> logging.Logger:
    """Create a logger that writes to both the console and a file."""
    logger = logging.getLogger("summarizer")
    if logger.handlers:  # don't add handlers twice
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


logger = setup_logging()

# HTTP codes worth retrying: rate limit + temporary server problems
RETRYABLE_CODES = {429, 500, 502, 503, 504}


def retry_with_backoff(max_retries: int = 4, base_delay: float = 1.0):
    """Retry a function with exponential backoff (1s, 2s, 4s, 8s...)."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    logger.info("API call succeeded in %.2fs", time.time() - start)
                    return result
                except (errors.APIError, httpx.TransportError) as e:
                    # API errors have a .code; network errors (timeout etc.) don't
                    code = getattr(e, "code", None)
                    retryable = code is None or code in RETRYABLE_CODES

                    if not retryable or attempt == max_retries:
                        logger.error("API call failed (code=%s): %s", code, e)
                        raise

                    delay = base_delay * (2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        "Attempt %d/%d failed (code=%s). Retrying in %.1fs...",
                        attempt + 1,
                        max_retries + 1,
                        code,
                        delay,
                    )
                    time.sleep(delay)

        return wrapper

    return decorator