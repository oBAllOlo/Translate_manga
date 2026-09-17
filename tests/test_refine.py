"""Unit tests for core.refine module — testing OpenRouter refine provider."""
import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


class TestCoreRefine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.work_dir = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_refine_chapter_happy_path(self):
        """Happy path: reads lens_translations.json, calls OpenRouter sequentially, writes llm_refined.json."""
        from core.refine import refine_chapter_work_dir

        lens_data = [
            {"page": 1, "thai": "สวัสดี นี่คือการทดสอบ", "translated_file": "page-001.jpg"},
            {"page": 2, "thai": "อะไรกันเนี่ย", "translated_file": "page-002.jpg"},
        ]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        mock_resp1 = MagicMock(status_code=200)
        mock_resp1.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "สวัสดี! นี่คือบทสนทนาทดสอบ",
                        "reasoning_details": [{"type": "thought", "text": "Friendly tone"}],
                    }
                }
            ]
        }

        mock_resp2 = MagicMock(status_code=200)
        mock_resp2.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "เกิดอะไรขึ้นเนี่ย!",
                        "reasoning_details": [{"type": "thought", "text": "Surprised expression"}],
                    }
                }
            ]
        }

        progress_calls = []

        def on_progress(done, total):
            progress_calls.append((done, total))

        async def run_test():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                mock_post.side_effect = [mock_resp1, mock_resp2]

                results = await refine_chapter_work_dir(
                    self.work_dir,
                    api_key="test-key",
                    on_progress=on_progress,
                )
                return results

        results = asyncio.run(run_test())

        # Verify output list
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["page"], 1)
        self.assertEqual(results[0]["original_text"], "สวัสดี นี่คือการทดสอบ")
        self.assertEqual(results[0]["refined_text"], "สวัสดี! นี่คือบทสนทนาทดสอบ")
        self.assertEqual(results[0]["provider"], "openrouter")
        self.assertEqual(results[0]["reasoning_details"], [{"type": "thought", "text": "Friendly tone"}])
        self.assertFalse(results[0].get("cached", False))

        self.assertEqual(results[1]["page"], 2)
        self.assertEqual(results[1]["original_text"], "อะไรกันเนี่ย")
        self.assertEqual(results[1]["refined_text"], "เกิดอะไรขึ้นเนี่ย!")

        # Verify llm_refined.json was written to disk
        refined_file = self.work_dir / "llm_refined.json"
        self.assertTrue(refined_file.exists())
        with open(refined_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0]["page"], 1)
        self.assertEqual(saved[0]["refined_text"], "สวัสดี! นี่คือบทสนทนาทดสอบ")

        # Verify progress callback was invoked
        self.assertEqual(progress_calls, [(1, 2), (2, 2)])

    def test_refine_caching_and_force(self):
        """Skip already refined pages unless force=True."""
        from core.refine import refine_chapter_work_dir

        lens_data = [
            {"page": 1, "thai": "หน้าหนึ่ง", "translated_file": "page-001.jpg"},
            {"page": 2, "thai": "หน้าสอง", "translated_file": "page-002.jpg"},
        ]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        # Pre-populate page 1 in llm_refined.json
        refined_existing = [
            {
                "page": 1,
                "original_text": "หน้าหนึ่ง",
                "refined_text": "หน้าหนึ่ง (ขัดเกลาเดิม)",
                "provider": "openrouter",
                "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
                "timestamp": "2026-09-16T10:00:00",
            }
        ]
        with open(self.work_dir / "llm_refined.json", "w", encoding="utf-8") as f:
            json.dump(refined_existing, f, ensure_ascii=False)

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "หน้าสอง (ขัดเกลาใหม่)"}}]
        }

        # Case A: force=False -> only page 2 is called on OpenRouter
        async def run_without_force():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                mock_post.return_value = mock_resp

                results = await refine_chapter_work_dir(self.work_dir, force=False, api_key="test-key")
                return results, mock_post.call_count

        results, post_count = asyncio.run(run_without_force())
        self.assertEqual(post_count, 1)  # Only page 2 called
        self.assertEqual(results[0]["refined_text"], "หน้าหนึ่ง (ขัดเกลาเดิม)")
        self.assertTrue(results[0]["cached"])
        self.assertEqual(results[1]["refined_text"], "หน้าสอง (ขัดเกลาใหม่)")
        self.assertFalse(results[1].get("cached", False))

        # Case B: force=True -> both pages are refined
        mock_force1 = MagicMock(status_code=200)
        mock_force1.json.return_value = {"choices": [{"message": {"content": "หน้าหนึ่ง (บังคับใหม่)"}}]}
        mock_force2 = MagicMock(status_code=200)
        mock_force2.json.return_value = {"choices": [{"message": {"content": "หน้าสอง (บังคับใหม่)"}}]}

        async def run_with_force():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                mock_post.side_effect = [mock_force1, mock_force2]

                results = await refine_chapter_work_dir(self.work_dir, force=True, api_key="test-key")
                return results, mock_post.call_count

        results_f, post_count_f = asyncio.run(run_with_force())
        self.assertEqual(post_count_f, 2)
        self.assertEqual(results_f[0]["refined_text"], "หน้าหนึ่ง (บังคับใหม่)")
        self.assertFalse(results_f[0].get("cached", False))

    def test_openrouter_missing_api_key_raises_error(self):
        """When OpenRouter API key is missing, OpenRouterAuthError is raised."""
        from core.refine import refine_chapter_work_dir, OpenRouterAuthError

        lens_data = [{"page": 1, "thai": "สวัสดี"}]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        async def run_missing_key():
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False):
                await refine_chapter_work_dir(self.work_dir, api_key="")

        with self.assertRaises(OpenRouterAuthError):
            asyncio.run(run_missing_key())

    def test_partial_failure_continues_processing(self):
        """If OpenRouter fails mid-batch on one page, the other pages still get refined and error is logged."""
        from core.refine import refine_chapter_work_dir

        lens_data = [
            {"page": 1, "thai": "สวัสดี"},
            {"page": 2, "thai": "มีข้อผิดพลาด"},
            {"page": 3, "thai": "กลับมาปกติ"},
        ]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        mock_ok1 = MagicMock(status_code=200)
        mock_ok1.json.return_value = {"choices": [{"message": {"content": "สวัสดีดีจ้า"}}]}

        mock_ok3 = MagicMock(status_code=200)
        mock_ok3.json.return_value = {"choices": [{"message": {"content": "กลับมาปกติแล้วนะ"}}]}

        async def run_partial():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                # Page 2 raises an exception
                mock_post.side_effect = [
                    mock_ok1,
                    Exception("OpenRouter timeout"),
                    mock_ok3,
                ]

                results = await refine_chapter_work_dir(self.work_dir, api_key="test-key")
                return results

        results = asyncio.run(run_partial())
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["refined_text"], "สวัสดีดีจ้า")
        self.assertIn("error", results[1])
        self.assertIn("OpenRouter timeout", results[1]["error"])
        self.assertEqual(results[2]["refined_text"], "กลับมาปกติแล้วนะ")

    def test_refine_single_page(self):
        """refine_single_page refines only the requested page."""
        from core.refine import refine_single_page

        lens_data = [
            {"page": 1, "thai": "หน้า 1"},
            {"page": 2, "thai": "หน้า 2"},
        ]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"choices": [{"message": {"content": "หน้า 2 ปรับปรุงแล้ว"}}]}

        async def run_single():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                mock_post.return_value = mock_resp

                res = await refine_single_page(self.work_dir, page_no=2, api_key="test-key")
                return res, mock_post.call_count

        res, post_count = asyncio.run(run_single())
        self.assertEqual(post_count, 1)
        self.assertEqual(res["page"], 2)
        self.assertEqual(res["refined_text"], "หน้า 2 ปรับปรุงแล้ว")
        self.assertEqual(res["provider"], "openrouter")

    def test_openrouter_provider_refine(self):
        """OpenRouterProvider sends headers, reasoning payload, and extracts reasoning_details."""
        from core.refine import OpenRouterProvider

        provider = OpenRouterProvider(api_key="test-api-key")
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "<dialogue>ข้าแต่ท่านผู้นำ!</dialogue>",
                        "reasoning_details": [{"type": "thought", "text": "Analyzing character dynamic..."}],
                    }
                }
            ]
        }

        async def run_or():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                out = await provider.refine("สวัสดีหัวหน้า")
                return out, mock_post.call_args

        out, call_args = asyncio.run(run_or())
        self.assertEqual(out.content, "ข้าแต่ท่านผู้นำ!")
        self.assertEqual(out.provider, "openrouter")
        self.assertEqual(out.reasoning_details, [{"type": "thought", "text": "Analyzing character dynamic..."}])

        # Verify headers & payload
        headers = call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer test-api-key")
        self.assertIn("HTTP-Referer", headers)
        self.assertIn("X-Title", headers)

        payload = call_args[1]["json"]
        self.assertEqual(payload["reasoning"], {"enabled": True})
        self.assertEqual(payload["model"], "nvidia/nemotron-3-ultra-550b-a55b:free")

    def test_openrouter_multi_turn_history_preservation(self):
        """Multi-turn touch-up preserves previous reasoning_details in assistant turn."""
        from core.refine import refine_single_page

        lens_data = [{"page": 1, "thai": "สวัสดี"}]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        # Pre-seed existing refined entry with reasoning_details
        refined_data = [
            {
                "page": 1,
                "original_text": "สวัสดี",
                "refined_text": "สวัสดีครับท่าน",
                "reasoning_details": [{"step": "thought_1"}],
                "provider": "openrouter",
                "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
            }
        ]
        with open(self.work_dir / "llm_refined.json", "w", encoding="utf-8") as f:
            json.dump(refined_data, f, ensure_ascii=False)

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "สวัสดีเพื่อนยาก",
                        "reasoning_details": [{"step": "thought_2"}],
                    }
                }
            ]
        }

        async def run_touchup():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                res = await refine_single_page(
                    self.work_dir,
                    page_no=1,
                    provider="openrouter",
                    api_key="test-key",
                    user_instruction="เปลี่ยนให้ดูเป็นเพื่อนสนิท",
                )
                return res, mock_post.call_args

        res, call_args = asyncio.run(run_touchup())
        self.assertEqual(res["refined_text"], "สวัสดีเพื่อนยาก")
        sent_messages = call_args[1]["json"]["messages"]

        # Check that previous assistant message with reasoning_details was preserved
        assistant_turn = next(m for m in sent_messages if m.get("role") == "assistant")
        self.assertEqual(assistant_turn["content"], "สวัสดีครับท่าน")
        self.assertEqual(assistant_turn["reasoning_details"], [{"step": "thought_1"}])

        # Check that new user instruction was appended
        last_turn = sent_messages[-1]
        self.assertEqual(last_turn["role"], "user")
        self.assertEqual(last_turn["content"], "เปลี่ยนให้ดูเป็นเพื่อนสนิท")

    def test_openrouter_rate_limit_retry_exhaustion(self):
        """When OpenRouter returns 429 repeatedly, it logs the rate limit error after retries."""
        from core.refine import refine_chapter_work_dir

        lens_data = [
            {"page": 1, "thai": "หน้า 1 ทดสอบ 429"},
        ]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        mock_429_resp = MagicMock(status_code=429, text="Rate limit exceeded")

        async def run_rate_limit():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                mock_post.return_value = mock_429_resp

                results = await refine_chapter_work_dir(
                    self.work_dir,
                    provider="openrouter",
                    api_key="test-key",
                )
                return results, mock_post.call_count

        results, post_count = asyncio.run(run_rate_limit())

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["page"], 1)
        self.assertEqual(post_count, 3)  # 3 attempts
        self.assertIn("error", results[0])
        self.assertIn("OpenRouterRateLimitError", results[0]["error"])


if __name__ == "__main__":
    unittest.main()



