"""Uploaded files: who can read them, and what a filename is allowed to do.

A document library is the part of a CMMS most likely to hold something that
matters — a contract, an inspection report, a photograph of a failure. Three
things have to hold: a filename cannot escape its directory, a tenant cannot
read another tenant's file, and a file big enough to exhaust the disk is
refused before it is written.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.multiTenantHelpers import (
    authHeaders,
    createTenantWithAdmin,
    loginAs,
    loginPlatform,
)
from tests.support.phase6Helpers import seedPlatform

MEGABYTE = 1024 * 1024


def uploadFile(client, headers, name: str, content: bytes, contentType: str = "text/plain"):
    return client.post(
        "/api/v1/documents",
        {"file": SimpleUploadedFile(name, content, content_type=contentType)},
        format="multipart",
        **headers,
    )


class FilenameSecurityTests(TestCase):
    """A filename is attacker-controlled input, not a label."""

    @classmethod
    def setUpTestData(cls) -> None:
        seedPlatform()
        cls.headers = authHeaders(loginPlatform(APIClient()))

    def setUp(self) -> None:
        self.client = APIClient()

    def testPathTraversalInTheFilenameCannotEscapeTheTenantDirectory(self) -> None:
        """`../../../etc/passwd` must become `passwd`, not a write outside
        the media root."""

        response = uploadFile(
            self.client,
            self.headers,
            "../../../../etc/passwd",
            b"root:x:0:0:",
        )
        self.assertIn(response.status_code, (200, 201), response.content)

        stored = response.json()["data"]
        self.assertNotIn("..", stored["name"])
        self.assertNotIn("/", stored["name"])
        self.assertEqual(stored["name"], "passwd")

    def testBackslashTraversalIsAlsoNeutralised(self) -> None:
        """Windows-style separators are the usual way past a `/`-only check."""

        response = uploadFile(
            self.client, self.headers, r"..\..\windows\system32\evil.dll", b"MZ"
        )
        self.assertIn(response.status_code, (200, 201), response.content)
        name = response.json()["data"]["name"]
        self.assertNotIn("..", name)
        self.assertNotIn("\\", name)

    def testAnEmptyFileIsRefused(self) -> None:
        response = uploadFile(self.client, self.headers, "empty.txt", b"")
        self.assertGreaterEqual(response.status_code, 400, response.content)

    def testAFileOverTheLimitIsRefused(self) -> None:
        """26 MB against a 25 MB ceiling. The point is that the refusal
        happens, not that it is graceful."""

        oversized = b"x" * (26 * MEGABYTE)
        response = uploadFile(self.client, self.headers, "huge.bin", oversized)
        self.assertGreaterEqual(
            response.status_code,
            400,
            "a file above the documented ceiling was accepted",
        )

    def testALargeButLegalFileSucceeds(self) -> None:
        """The limit must not be so eager that a real scanned PDF fails."""

        payload = b"%PDF-1.4\n" + b"0" * (5 * MEGABYTE)
        response = uploadFile(
            self.client, self.headers, "scan.pdf", payload, "application/pdf"
        )
        self.assertIn(response.status_code, (200, 201), response.content[:400])
        self.assertEqual(response.json()["data"]["sizeBytes"], len(payload))


class FileTenantIsolationTests(TestCase):
    """Tenant A must not be able to download tenant B's documents."""

    @classmethod
    def setUpTestData(cls) -> None:
        seedPlatform()
        cls.tenantB = createTenantWithAdmin("files-b")
        cls.headersA = authHeaders(loginPlatform(APIClient()))
        cls.headersB = authHeaders(loginAs(APIClient(), cls.tenantB))

    def setUp(self) -> None:
        self.client = APIClient()

    def testAnotherTenantsDocumentIsNotListed(self) -> None:
        uploaded = uploadFile(
            APIClient(), self.headersB, "b-secret.txt", b"tenant B private"
        )
        self.assertIn(uploaded.status_code, (200, 201), uploaded.content)

        listed = self.client.get("/api/v1/documents", **self.headersA)
        self.assertEqual(listed.status_code, 200, listed.content)
        names = [row["name"] for row in listed.json()["data"]]
        self.assertNotIn("b-secret.txt", names)

    def testAnotherTenantsDocumentCannotBeDownloadedById(self) -> None:
        """The one that matters. Listing can be filtered correctly while the
        download endpoint fetches by primary key and forgets the tenant."""

        uploaded = uploadFile(
            APIClient(), self.headersB, "b-contract.txt", b"tenant B contract"
        )
        self.assertIn(uploaded.status_code, (200, 201), uploaded.content)
        documentId = uploaded.json()["data"]["id"]

        response = self.client.get(
            f"/api/v1/documents/{documentId}/download", **self.headersA
        )
        self.assertIn(
            response.status_code,
            (403, 404),
            f"tenant A downloaded tenant B's file (status {response.status_code})",
        )
        if response.status_code < 400:
            body = b"".join(response.streaming_content)
            self.assertNotIn(b"tenant B contract", body)

    def testAnotherTenantCannotDeleteYourDocument(self) -> None:
        uploaded = uploadFile(
            APIClient(), self.headersB, "b-delete-me.txt", b"still needed"
        )
        self.assertIn(uploaded.status_code, (200, 201), uploaded.content)
        documentId = uploaded.json()["data"]["id"]

        response = self.client.delete(
            f"/api/v1/documents/{documentId}", **self.headersA
        )
        self.assertIn(response.status_code, (403, 404), response.content)

        # The file must still be there for its owner.
        stillThere = APIClient().get("/api/v1/documents", **self.headersB)
        names = [row["name"] for row in stillThere.json()["data"]]
        self.assertIn("b-delete-me.txt", names)


class UnauthenticatedAccessTests(TestCase):
    """No token, no file."""

    @classmethod
    def setUpTestData(cls) -> None:
        seedPlatform()
        cls.headers = authHeaders(loginPlatform(APIClient()))

    def setUp(self) -> None:
        self.client = APIClient()

    def testDownloadRequiresAuthentication(self) -> None:
        uploaded = uploadFile(
            APIClient(), self.headers, "private.txt", b"not for anonymous eyes"
        )
        self.assertIn(uploaded.status_code, (200, 201), uploaded.content)
        documentId = uploaded.json()["data"]["id"]

        response = APIClient().get(f"/api/v1/documents/{documentId}/download")
        self.assertIn(response.status_code, (401, 403), response.content)

    def testListingRequiresAuthentication(self) -> None:
        response = APIClient().get("/api/v1/documents")
        self.assertIn(response.status_code, (401, 403), response.content)


class ContentHandlingTests(TestCase):
    """What comes back out when a file is downloaded."""

    @classmethod
    def setUpTestData(cls) -> None:
        seedPlatform()
        cls.headers = authHeaders(loginPlatform(APIClient()))

    def setUp(self) -> None:
        self.client = APIClient()

    def testDownloadIsAnAttachmentNotAnInlineRender(self) -> None:
        """An HTML file served inline from the API origin is stored XSS. The
        response must tell the browser to download, not render."""

        uploaded = uploadFile(
            self.client,
            self.headers,
            "payload.html",
            b"<script>alert(document.cookie)</script>",
            "text/html",
        )
        self.assertIn(uploaded.status_code, (200, 201), uploaded.content)
        documentId = uploaded.json()["data"]["id"]

        response = self.client.get(
            f"/api/v1/documents/{documentId}/download", **self.headers
        )
        # FileResponse streams; `.content` raises, so never put it in a message.
        self.assertEqual(response.status_code, 200)
        disposition = response.headers.get("Content-Disposition", "")
        self.assertIn(
            "attachment",
            disposition,
            f"an uploaded HTML file is served inline: {disposition!r}",
        )

    def testRoundTripPreservesTheBytesExactly(self) -> None:
        payload = bytes(range(256)) * 64
        uploaded = uploadFile(
            self.client, self.headers, "binary.bin", payload, "application/octet-stream"
        )
        self.assertIn(uploaded.status_code, (200, 201), uploaded.content)
        documentId = uploaded.json()["data"]["id"]

        response = self.client.get(
            f"/api/v1/documents/{documentId}/download", **self.headers
        )
        self.assertEqual(response.status_code, 200)
        downloaded = b"".join(response.streaming_content)
        self.assertEqual(downloaded, payload, "the stored file differs from the upload")

    def testAUnicodeFilenameSurvivesTheDownloadHeader(self) -> None:
        """Persian filenames are the norm here, and a naive header breaks on
        the first non-ASCII byte."""

        uploaded = uploadFile(
            self.client, self.headers, "گزارش بازرسی.txt", "محتوا".encode()
        )
        self.assertIn(uploaded.status_code, (200, 201), uploaded.content)
        documentId = uploaded.json()["data"]["id"]

        response = self.client.get(
            f"/api/v1/documents/{documentId}/download", **self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("filename*=", response.headers.get("Content-Disposition", ""))
