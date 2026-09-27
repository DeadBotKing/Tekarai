"""Tenant document library — public REST contract (Phase 31).

A shared per-tenant Files-of-Record library: multipart upload stores the byte
stream under MEDIA storage, metadata is searchable, downloads stream the file
back with its original name, and delete soft-removes the row while purging the
stored bytes. Tenant isolation and permission gates are exercised end-to-end.
"""

from __future__ import annotations

import io

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.phase6Helpers import loginViaApi, seedPlatform


class DocumentsApiTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def uploadDoc(
        self, name: str = "دستورالعمل-ایمنی.pdf", category: str = "ایمنی"
    ) -> dict:
        fileBody = io.BytesIO(b"%PDF-1.4 demo bytes for the document library")
        fileBody.name = name
        response = self.client.post(
            "/api/v1/documents",
            {"file": fileBody, "category": category, "description": "نسخه‌ی ۱"},
            format="multipart",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def testUploadListDownloadAndDeleteRoundTrip(self) -> None:
        uploaded = self.uploadDoc()
        self.assertEqual(uploaded["name"], "دستورالعمل-ایمنی.pdf")
        self.assertEqual(uploaded["category"], "ایمنی")
        self.assertGreater(uploaded["sizeBytes"], 0)

        listing = self.client.get("/api/v1/documents", **self.auth)
        self.assertEqual(listing.status_code, 200, listing.content)
        names = [item["name"] for item in listing.json()["data"]]
        self.assertIn("دستورالعمل-ایمنی.pdf", names)

        download = self.client.get(
            f"/api/v1/documents/{uploaded['id']}/download", **self.auth
        )
        self.assertEqual(download.status_code, 200, download.status_code)
        body = b"".join(download.streaming_content)
        self.assertTrue(body.startswith(b"%PDF"))

        deleted = self.client.delete(f"/api/v1/documents/{uploaded['id']}", **self.auth)
        self.assertEqual(deleted.status_code, 200, deleted.content)

        goneDownload = self.client.get(
            f"/api/v1/documents/{uploaded['id']}/download", **self.auth
        )
        self.assertEqual(goneDownload.status_code, 404)

    def testSearchFiltersByNameAndCategory(self) -> None:
        self.uploadDoc("safety-manual.pdf", "ایمنی")
        self.uploadDoc("pump-datasheet.pdf", "مهندسی")

        searched = self.client.get("/api/v1/documents?search=pump", **self.auth)
        self.assertEqual(searched.status_code, 200, searched.content)
        payload = searched.json()
        names = [item["name"] for item in payload["data"]]
        self.assertEqual(names, ["pump-datasheet.pdf"])

        byCategory = self.client.get("/api/v1/documents?category=ایمنی", **self.auth)
        self.assertEqual(byCategory.status_code, 200, byCategory.content)
        names = [item["name"] for item in byCategory.json()["data"]]
        self.assertEqual(names, ["safety-manual.pdf"])

    def testUploadWithoutFileIsRejected(self) -> None:
        response = self.client.post(
            "/api/v1/documents", {"category": "x"}, format="multipart", **self.auth
        )
        self.assertEqual(response.status_code, 400)

    def testAnonymousAccessIsDenied(self) -> None:
        response = APIClient().get("/api/v1/documents")
        self.assertEqual(response.status_code, 401)
