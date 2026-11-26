import asyncio
import unittest

import httpx
from unittest.mock import AsyncMock, patch

from app import main


class LiveDiscoveryCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        main._discovery_cache_rows = None
        main._discovery_cache_report = {"status": "unknown", "partial": True}
        main._discovery_cache_expires_at = 0.0

    async def asyncTearDown(self):
        main._discovery_cache_rows = None
        main._discovery_cache_report = {"status": "unknown", "partial": True}
        main._discovery_cache_expires_at = 0.0

    async def test_recent_scan_is_reused_and_returned_as_a_copy(self):
        rows = [{"id": 1, "title": "Example scholarship", "criteria": []}]
        with patch.object(main, "discover_live_scholarships", new=AsyncMock(return_value=rows)) as discover:
            first = await main._live_results()
            first[0]["title"] = "Changed by caller"
            second = await main._live_results()

        self.assertEqual(discover.await_count, 1)
        self.assertEqual(second[0]["title"], "Example scholarship")
        self.assertIsNot(first, second)

    async def test_concurrent_requests_share_one_provider_scan(self):
        rows = [{"id": 2, "title": "Concurrent scholarship"}]

        async def slow_scan():
            await asyncio.sleep(0.01)
            return rows

        with patch.object(main, "discover_live_scholarships", new=AsyncMock(side_effect=slow_scan)) as discover:
            first, second, third = await asyncio.gather(
                main._live_results(),
                main._live_results(),
                main._live_results(),
            )

        self.assertEqual(discover.await_count, 1)
        self.assertEqual(first, second)
        self.assertEqual(second, third)

    async def test_expired_cache_triggers_a_fresh_scan(self):
        rows = [{"id": 3, "title": "Fresh scholarship"}]
        with patch.object(main, "discover_live_scholarships", new=AsyncMock(return_value=rows)) as discover:
            await main._live_results()
            main._discovery_cache_expires_at = 0.0
            await main._live_results()

        self.assertEqual(discover.await_count, 2)


    async def test_discovery_status_exposes_partial_coverage_metadata(self):
        main._discovery_cache_report = {
            "status": "partial",
            "partial": True,
            "total_sources": 10,
            "completed_sources": 7,
            "timed_out_sources": ["Slow provider"],
            "failed_sources": [],
            "sources_with_unavailable_pages": ["Blocked provider"],
            "pages_attempted": 12,
            "pages_succeeded": 9,
            "pages_unavailable": 2,
            "pages_cancelled": 1,
        }
        transport = httpx.ASGITransport(app=main.app)
        with patch.object(main, "_live_results", new=AsyncMock(return_value=[])):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/discovery-status")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["partial"])
        self.assertEqual(response.json()["timed_out_sources"], ["Slow provider"])


if __name__ == "__main__":
    unittest.main()
