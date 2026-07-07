import json
import logging
import time

import httpx

from career_scout_ai.llm import ScoringResult

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """HTTP client for the OpenRouter cloud LLM API."""

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemini-2.5-flash-preview-05-20",
        timeout: int = 60,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def score_offer(self, system_prompt: str, user_prompt: str) -> ScoringResult | None:
        """Call OpenRouter to score an offer. Returns None if all retries fail."""
        for attempt in range(1, self.max_retries + 1):
            try:
                result = self._call(system_prompt, user_prompt)
                if result is not None:
                    return result
                logger.warning(
                    "Attempt %d/%d: invalid response format",
                    attempt,
                    self.max_retries,
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    logger.error(
                        "OpenRouter auth error — check OPENROUTER_API_KEY: %s", e
                    )
                    return None
                logger.warning("Attempt %d/%d failed: %s", attempt, self.max_retries, e)
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.warning("Attempt %d/%d failed: %s", attempt, self.max_retries, e)

            if attempt < self.max_retries:
                backoff = 2**attempt
                time.sleep(backoff)

        logger.error("All %d attempts failed, skipping offer", self.max_retries)
        return None

    def _call(self, system_prompt: str, user_prompt: str) -> ScoringResult | None:
        """Make a single request to OpenRouter /chat/completions."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://career-scout-ai.local",
            "X-Title": "Career Scout AI",
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return self._parse_response(content)

    def _parse_response(self, content: str) -> ScoringResult | None:
        """Parse JSON response into ScoringResult."""
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON: %s", content[:200])
            return None

        score = parsed.get("score")
        summary = parsed.get("summary")

        if score is None or summary is None:
            logger.warning("Missing fields in response: %s", parsed)
            return None

        score = max(0.0, min(1.0, float(score)))
        return ScoringResult(score=score, summary=summary)

    def is_available(self) -> bool:
        """Check that the API key is set and accepted by OpenRouter."""
        if not self.api_key:
            msg = "OpenRouter API key not configured (set OPENROUTER_API_KEY)"
            logger.error(msg)
            return False
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(
                    f"{OPENROUTER_BASE_URL}/auth/key",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                is_ok: bool = resp.status_code == 200
                return is_ok
        except (httpx.HTTPError, httpx.TimeoutException):
            return False
