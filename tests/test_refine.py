"""Unit tests for core.refine module — testing at the core/refine.py seam."""
import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# We will import from core.refine once implemented
# from core.refine import refine_chapter_work_dir, check_ollama_health, refine_single_page, OllamaError


class TestCoreRefine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.work_dir = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_refine_chapter_happy_path(self):
        """Happy path: reads lens_translations.json, calls Ollama sequentially, writes llm_refined.json."""
        from core.refine import refine_chapter_work_dir

        lens_data = [
            {"page": 1, "thai": "สวัสดี นี่คือการทดสอบ", "translated_file": "page-001.jpg"},
            {"page": 2, "thai": "อะไรกันเนี่ย", "translated_file": "page-002.jpg"},
        ]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        mock_tags_resp = MagicMock(status_code=200)
        mock_tags_resp.json.return_value = {
            "models": [{"name": "gemma4:e4b"}, {"name": "llama3:latest"}]
        }

        mock_chat_resp1 = MagicMock(status_code=200)
        mock_chat_resp1.json.return_value = {
            "message": {"content": "สวัสดี! นี่คือบทสนทนาทดสอบ"}
        }

        mock_chat_resp2 = MagicMock(status_code=200)
        mock_chat_resp2.json.return_value = {
            "message": {"content": "เกิดอะไรขึ้นเนี่ย!"}
        }

        progress_calls = []

        def on_progress(done, total):
            progress_calls.append((done, total))

        async def run_test():
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_get.return_value = mock_tags_resp
                mock_post.side_effect = [mock_chat_resp1, mock_chat_resp2]

                results = await refine_chapter_work_dir(
                    self.work_dir,
                    on_progress=on_progress,
                )
                return results

        results = asyncio.run(run_test())

        # Verify output list
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["page"], 1)
        self.assertEqual(results[0]["original_text"], "สวัสดี นี่คือการทดสอบ")
        self.assertEqual(results[0]["refined_text"], "สวัสดี! นี่คือบทสนทนาทดสอบ")
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
                "model": "gemma4:e4b",
                "timestamp": "2026-09-16T10:00:00",
            }
        ]
        with open(self.work_dir / "llm_refined.json", "w", encoding="utf-8") as f:
            json.dump(refined_existing, f, ensure_ascii=False)

        mock_tags_resp = MagicMock(status_code=200)
        mock_tags_resp.json.return_value = {"models": [{"name": "gemma4:e4b"}]}

        mock_chat_resp = MagicMock(status_code=200)
        mock_chat_resp.json.return_value = {
            "message": {"content": "หน้าสอง (ขัดเกลาใหม่)"}
        }

        # Case A: force=False -> only page 2 is called on Ollama
        async def run_without_force():
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_get.return_value = mock_tags_resp
                mock_post.return_value = mock_chat_resp

                results = await refine_chapter_work_dir(self.work_dir, force=False)
                return results, mock_post.call_count

        results, post_count = asyncio.run(run_without_force())
        self.assertEqual(post_count, 1)  # Only page 2 called
        self.assertEqual(results[0]["refined_text"], "หน้าหนึ่ง (ขัดเกลาเดิม)")
        self.assertTrue(results[0]["cached"])
        self.assertEqual(results[1]["refined_text"], "หน้าสอง (ขัดเกลาใหม่)")
        self.assertFalse(results[1].get("cached", False))

        # Case B: force=True -> both pages are refined
        mock_chat_force1 = MagicMock(status_code=200)
        mock_chat_force1.json.return_value = {"message": {"content": "หน้าหนึ่ง (บังคับใหม่)"}}
        mock_chat_force2 = MagicMock(status_code=200)
        mock_chat_force2.json.return_value = {"message": {"content": "หน้าสอง (บังคับใหม่)"}}

        async def run_with_force():
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_get.return_value = mock_tags_resp
                mock_post.side_effect = [mock_chat_force1, mock_chat_force2]

                results = await refine_chapter_work_dir(self.work_dir, force=True)
                return results, mock_post.call_count

        results_f, post_count_f = asyncio.run(run_with_force())
        self.assertEqual(post_count_f, 2)
        self.assertEqual(results_f[0]["refined_text"], "หน้าหนึ่ง (บังคับใหม่)")
        self.assertFalse(results_f[0].get("cached", False))

    def test_ollama_unreachable_raises_error(self):
        """When Ollama is down, check_ollama_health raises an informative error."""
        import httpx
        from core.refine import refine_chapter_work_dir, OllamaConnectionError

        lens_data = [{"page": 1, "thai": "สวัสดี"}]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        async def run_failing():
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.side_effect = httpx.ConnectError("Connection refused")
                await refine_chapter_work_dir(self.work_dir)

        with self.assertRaises(OllamaConnectionError):
            asyncio.run(run_failing())

    def test_ollama_model_missing_raises_error(self):
        """When Ollama is up but model is not present, raises OllamaModelError."""
        from core.refine import refine_chapter_work_dir, OllamaModelError

        lens_data = [{"page": 1, "thai": "สวัสดี"}]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        mock_tags_resp = MagicMock(status_code=200)
        mock_tags_resp.json.return_value = {"models": [{"name": "other-model:latest"}]}

        async def run_missing_model():
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_tags_resp
                await refine_chapter_work_dir(self.work_dir, model="gemma4:e4b")

        with self.assertRaises(OllamaModelError):
            asyncio.run(run_missing_model())


    def test_partial_failure_continues_processing(self):
        """If Ollama fails mid-batch on one page, the other pages still get refined and error is logged."""
        from core.refine import refine_chapter_work_dir

        lens_data = [
            {"page": 1, "thai": "สวัสดี"},
            {"page": 2, "thai": "มีข้อผิดพลาด"},
            {"page": 3, "thai": "กลับมาปกติ"},
        ]
        with open(self.work_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

        mock_tags_resp = MagicMock(status_code=200)
        mock_tags_resp.json.return_value = {"models": [{"name": "gemma4:e4b"}]}

        mock_ok1 = MagicMock(status_code=200)
        mock_ok1.json.return_value = {"message": {"content": "สวัสดีดีจ้า"}}

        mock_ok3 = MagicMock(status_code=200)
        mock_ok3.json.return_value = {"message": {"content": "กลับมาปกติแล้วนะ"}}

        async def run_partial():
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_get.return_value = mock_tags_resp
                # Page 2 raises an exception
                mock_post.side_effect = [
                    mock_ok1,
                    Exception("Ollama timeout"),
                    mock_ok3,
                ]

                results = await refine_chapter_work_dir(self.work_dir)
                return results

        results = asyncio.run(run_partial())
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["refined_text"], "สวัสดีดีจ้า")
        self.assertIn("error", results[1])
        self.assertIn("Ollama timeout", results[1]["error"])
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

        mock_tags_resp = MagicMock(status_code=200)
        mock_tags_resp.json.return_value = {"models": [{"name": "gemma4:e4b"}]}

        mock_chat_resp = MagicMock(status_code=200)
        mock_chat_resp.json.return_value = {"message": {"content": "หน้า 2 ปรับปรุงแล้ว"}}

        async def run_single():
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_get.return_value = mock_tags_resp
                mock_post.return_value = mock_chat_resp

                res = await refine_single_page(self.work_dir, page_no=2)
                return res, mock_post.call_count

        res, call_count = asyncio.run(run_single())
        self.assertEqual(call_count, 1)
        self.assertEqual(res["page"], 2)
        self.assertEqual(res["refined_text"], "หน้า 2 ปรับปรุงแล้ว")


if __name__ == "__main__":
    unittest.main()

