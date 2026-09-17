"""Tests for backend.app.services.job_runner module."""
import unittest
from pathlib import Path


class TestJobRunnerImports(unittest.TestCase):
    def test_job_runner_symbols_defined(self):
        """Verify that helper symbols imported by job_runner are defined and callable."""
        from backend.app.services.job_runner import (
            _get_session,
            _fetch_image,
            _mangadex_fallback,
            _unwrap_spoilerhat,
            _download_one_page,
            _run_overlapping_pipeline,
        )

        self.assertTrue(callable(_get_session))
        self.assertTrue(callable(_fetch_image))
        self.assertTrue(callable(_mangadex_fallback))
        self.assertTrue(callable(_unwrap_spoilerhat))
        self.assertTrue(callable(_download_one_page))
        self.assertTrue(callable(_run_overlapping_pipeline))

        # Test _get_session returns a valid requests.Session
        session = _get_session()
        self.assertIsNotNone(session)
        self.assertIn("User-Agent", session.headers)


if __name__ == "__main__":
    unittest.main()
