import logging
import time

import requests


class Client:
    def __init__(self, timeout=60, attempts=3):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "au-da-pipeline/1.0 (public development register research)"
        self.timeout = timeout
        self.attempts = attempts

    def json(self, method, url, **kwargs):
        for attempt in range(self.attempts):
            try:
                r = self.session.request(method, url, timeout=(15, self.timeout), **kwargs)
                r.raise_for_status()
                result = r.json()
                if isinstance(result, dict) and result.get("error"):
                    raise ValueError("API error: " + str(result["error"])[:300])
                return result
            except (requests.RequestException, ValueError) as exc:
                retryable = not isinstance(exc, requests.HTTPError) or (
                    exc.response.status_code in [408, 429] or exc.response.status_code >= 500
                )
                if attempt == self.attempts - 1 or not retryable:
                    raise
                wait = min(2 ** attempt, 30)
                if isinstance(exc, requests.HTTPError):
                    retry_after = exc.response.headers.get("Retry-After", "")
                    if retry_after.isdigit():
                        wait = min(int(retry_after), 60)
                logging.getLogger("pipeline.http").warning(
                    "%s request failed (%s); retry %d/%d in %ss", url, type(exc).__name__,
                    attempt + 1, self.attempts, wait,
                )
                time.sleep(wait)

    def close(self):
        self.session.close()
