import unittest
from unittest.mock import patch

import ai_router


class FakeResponse:
    def __init__(self, status_code=429, headers=None, body=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.text = text

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body if self._body is not None else {}


class AIRouterTests(unittest.TestCase):
    def setUp(self):
        ai_router._PROVIDER_COOLDOWN_UNTIL.clear()
        ai_router._GEMINI_KEY_COOLDOWN_UNTIL.clear()

    def tearDown(self):
        ai_router._PROVIDER_COOLDOWN_UNTIL.clear()
        ai_router._GEMINI_KEY_COOLDOWN_UNTIL.clear()

    def test_retry_after_is_parsed_and_capped_without_sleeping(self):
        response = FakeResponse(
            headers={"Retry-After": "120"},
        )
        delay = ai_router._provider_retry_delay(response, 429)

        self.assertEqual(delay, 120.25)
        with patch("ai_router.time.sleep") as sleep:
            ai_router._mark_cooldown("groq", 429, delay)
            sleep.assert_not_called()

        self.assertTrue(ai_router._is_cooled_down("groq"))

    def test_groq_429_fails_over_to_gemini(self):
        calls = []

        def fake_has_key(provider):
            return provider in {"groq", "gemini"}

        def fake_request(provider, messages, tools):
            calls.append(provider)
            if provider == "groq":
                ai_router._mark_cooldown("groq", 429, 120)
                return None, "HTTP 429: simulated rate limit"
            return {"role": "assistant", "content": "Gemini fallback worked."}, None

        with patch.object(ai_router, "_provider_has_key", side_effect=fake_has_key), patch.object(
            ai_router, "_request", side_effect=fake_request
        ):
            result = ai_router.call_ai([{"role": "user", "content": "test"}], [])

        self.assertEqual(result["content"], "Gemini fallback worked.")
        self.assertEqual(calls, ["groq", "gemini"])

    def test_cooled_provider_is_skipped_before_request(self):
        calls = []
        ai_router._mark_cooldown("groq", 429, 120)

        def fake_has_key(provider):
            return provider in {"groq", "gemini"}

        def fake_request(provider, messages, tools):
            calls.append(provider)
            return {"role": "assistant", "content": "ok"}, None

        with patch.object(ai_router, "_provider_has_key", side_effect=fake_has_key), patch.object(
            ai_router, "_request", side_effect=fake_request
        ):
            result = ai_router.call_ai([{"role": "user", "content": "test"}], [])

        self.assertEqual(result["content"], "ok")
        self.assertEqual(calls, ["gemini"])

    def test_gemini_key_limit_does_not_sleep(self):
        key = "fake-gemini-key"
        response = FakeResponse(
            status_code=429,
            headers={"retry-after": "45s"},
            text="rate limited",
        )
        ai_router._GEMINI_KEY_COOLDOWN_UNTIL.clear()

        with patch.dict("os.environ", {"GEMINI_API_KEY": key}, clear=False), patch(
            "ai_router.requests.post", return_value=response
        ) as post, patch("ai_router.time.sleep") as sleep:
            message, error = ai_router._request(
                "gemini", [{"role": "user", "content": "test"}], []
            )

        self.assertIsNone(message)
        self.assertIn("Gemini key limited", error)
        self.assertTrue(post.called)
        sleep.assert_not_called()
        self.assertTrue(ai_router._key_cooled_down(key))

    def test_all_available_providers_failed_returns_clear_error(self):
        def fake_has_key(provider):
            return provider in {"groq", "gemini"}

        def fake_request(provider, messages, tools):
            return None, f"{provider} failed"

        with patch.object(ai_router, "_provider_has_key", side_effect=fake_has_key), patch.object(
            ai_router, "_request", side_effect=fake_request
        ):
            with self.assertRaisesRegex(RuntimeError, "All available AI providers failed"):
                ai_router.call_ai([{"role": "user", "content": "test"}], [])


if __name__ == "__main__":
    unittest.main()
