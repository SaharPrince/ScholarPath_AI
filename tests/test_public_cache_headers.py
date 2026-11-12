import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app import main


class PublicScholarshipCacheHeaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_scholarship_get_is_briefly_edge_cacheable(self):
        rows = [{"id": 1, "title": "Example", "status": "unverified"}]
        transport = httpx.ASGITransport(app=main.app)
        with patch.object(main, "_live_results", new=AsyncMock(return_value=rows)):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/scholarships?status=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("cache-control"),
            "public, s-maxage=15, stale-while-revalidate=15",
        )

    async def test_profile_matching_post_is_never_publicly_cached(self):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/match", json={})

        self.assertEqual(response.status_code, 422)
        self.assertIsNone(response.headers.get("cache-control"))

    async def test_failed_scholarship_response_is_not_cached(self):
        transport = httpx.ASGITransport(app=main.app)
        with patch.object(main, "_live_results", new=AsyncMock(return_value=[])):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/scholarships/999")

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(response.headers.get("cache-control"))


if __name__ == "__main__":
    unittest.main()
