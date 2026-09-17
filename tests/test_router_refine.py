"""Tests for chapters router refine endpoints."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.services.job_runner import OUTPUT_ROOT


class TestRouterRefine(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.test_chapter = "test-chapter-refine"
        self.chapter_dir = OUTPUT_ROOT / self.test_chapter
        self.chapter_dir.mkdir(parents=True, exist_ok=True)

        # Create manifest
        manifest = {
            "title": "Test Chapter Refine",
            "page_count": 2,
            "pages": [
                {"page": 1, "file": "page-001.jpg"},
                {"page": 2, "file": "page-002.jpg"},
            ],
        }
        with open(self.chapter_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        # Create lens_translations
        lens_data = [
            {"page": 1, "thai": "สวัสดีจากเลนส์", "translated_file": "page-001.jpg"},
            {"page": 2, "thai": "ลาก่อนจากเลนส์", "translated_file": "page-002.jpg"},
        ]
        with open(self.chapter_dir / "lens_translations.json", "w", encoding="utf-8") as f:
            json.dump(lens_data, f, ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.chapter_dir, ignore_errors=True)

    def test_get_chapter_with_refined_data(self):
        # Before refinement: has_refined is False
        resp = self.client.get(f"/api/chapters/{self.test_chapter}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["has_refined"])
        self.assertEqual(data["pages"][0]["original_text"], "สวัสดีจากเลนส์")
        self.assertIsNone(data["pages"][0]["refined_text"])

        # Add llm_refined.json
        refined_data = [
            {"page": 1, "original_text": "สวัสดีจากเลนส์", "refined_text": "สวัสดีครับท่านผู้อ่าน"},
        ]
        with open(self.chapter_dir / "llm_refined.json", "w", encoding="utf-8") as f:
            json.dump(refined_data, f, ensure_ascii=False)

        resp2 = self.client.get(f"/api/chapters/{self.test_chapter}")
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2["has_refined"])
        self.assertEqual(data2["pages"][0]["refined_text"], "สวัสดีครับท่านผู้อ่าน")

    def test_post_refine_chapter(self):
        with patch("backend.app.routers.chapters.run_refine_job", new_callable=AsyncMock) as mock_run:
            resp = self.client.post(f"/api/chapters/{self.test_chapter}/refine", json={"force": True})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("job_id", data)

    def test_post_refine_single_page(self):
        mock_res = {
            "page": 1,
            "original_text": "สวัสดีจากเลนส์",
            "refined_text": "สวัสดีครับผม",
            "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "provider": "openrouter",
            "cached": False,
        }
        with patch("backend.app.routers.chapters.refine_single_page", new_callable=AsyncMock) as mock_refine:
            mock_refine.return_value = mock_res
            resp = self.client.post(
                f"/api/chapters/{self.test_chapter}/pages/1/refine",
                json={"force": False}
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["page"], 1)
            self.assertEqual(data["refined_text"], "สวัสดีครับผม")

    def test_post_refine_page_with_openrouter_and_instruction(self):

        mock_res = {
            "page": 1,
            "original_text": "สวัสดีจากเลนส์",
            "refined_text": "สวัสดีครับท่านหัวหน้า",
            "reasoning_details": [{"step": "thought_ok"}],
            "provider": "openrouter",
            "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "cached": False,
        }
        with patch("backend.app.routers.chapters.refine_single_page", new_callable=AsyncMock) as mock_refine:
            mock_refine.return_value = mock_res
            resp = self.client.post(
                f"/api/chapters/{self.test_chapter}/pages/1/refine",
                json={
                    "force": True,
                    "provider": "openrouter",
                    "api_key": "test-key-123",
                    "user_instruction": "ทำให้เป็นทางการ",
                }
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["refined_text"], "สวัสดีครับท่านหัวหน้า")
            self.assertEqual(data["provider"], "openrouter")
            self.assertEqual(data["reasoning_details"], [{"step": "thought_ok"}])

            # Verify arguments passed to core
            mock_refine.assert_called_once()
            call_kwargs = mock_refine.call_args[1]
            self.assertEqual(call_kwargs["provider"], "openrouter")
            self.assertEqual(call_kwargs["api_key"], "test-key-123")
            self.assertEqual(call_kwargs["user_instruction"], "ทำให้เป็นทางการ")

    def test_post_refine_page_stream_endpoint(self):
        async def fake_stream(*args, **kwargs):
            yield "event: start\ndata: {\"provider\": \"openrouter\"}\n\n"
            yield "event: content\ndata: {\"delta\": \"สวัสดี\"}\n\n"
            yield "event: done\ndata: {\"refined_text\": \"สวัสดี\"}\n\n"

        with patch("backend.app.routers.chapters.stream_refine_page", side_effect=fake_stream):
            resp = self.client.post(
                f"/api/chapters/{self.test_chapter}/pages/1/refine/stream",
                json={"provider": "openrouter"}
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/event-stream", resp.headers["content-type"])
            self.assertIn("event: content", resp.text)


if __name__ == "__main__":
    unittest.main()

