"""Content-Disposition must survive a non-ASCII filename.

Every export endpoint used to build the header by hand:

    response["Content-Disposition"] = f'attachment; filename="{filename}"'

For the device maintenance report the filename embeds `device.code`, which is
user-supplied and may be Persian. Django cannot put a non-Latin-1 byte in a
header, so it falls back to RFC 2047 and base64-encodes the *entire* value --
including the word `attachment`. The browser then receives a header it cannot
parse at all: the download name is lost and the attachment disposition goes
with it, so the file may be rendered inline instead of saved.

RFC 6266/5987 defines `filename*=utf-8''<percent-encoded>` for exactly this,
and Django ships `content_disposition_header()` to emit it. These tests pin
the two properties that matter: the disposition type stays readable, and the
original name is recoverable.
"""

from __future__ import annotations

import urllib.parse

from django.core.cache import cache
from django.test import TestCase
from django.utils.http import content_disposition_header
from rest_framework.test import APIClient

from tests.support.phase6Helpers import loginViaApi, seedPlatform

PERSIAN_CODE = "پرس-۱۰۱"


class ExportFilenameEncodingTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def assertUsableAttachmentHeader(self, header: str, expectedName: str) -> None:
        """The header must stay parseable and must carry `expectedName`."""
        self.assertFalse(
            header.startswith("=?"),
            f"header was RFC 2047 encoded as a whole and is unparseable: {header!r}",
        )
        self.assertTrue(
            header.startswith("attachment"),
            f"disposition type was lost: {header!r}",
        )
        if expectedName.isascii():
            self.assertIn(expectedName, header)
            return
        self.assertIn("filename*=utf-8''", header)
        encoded = header.split("filename*=utf-8''", 1)[1].split(";", 1)[0]
        self.assertEqual(urllib.parse.unquote(encoded), expectedName)

    def testAsciiExportNameIsUnchanged(self) -> None:
        response = self.client.get(
            "/api/v1/maintenance/work-orders", {"export": "csv"}, **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertUsableAttachmentHeader(response["Content-Disposition"], "work-orders.csv")

    def testPersianDeviceCodeSurvivesTheExportHeader(self) -> None:
        created = self.client.post(
            "/api/v1/maintenance/devices",
            {
                "code": PERSIAN_CODE,
                "name": "پرس هیدرولیک خط ۱",
                "location": "سالن A",
                "department": "mechanical",
                "pmIntervalDays": 30,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(created.status_code, 201, created.content)
        deviceId = created.json()["data"]["id"]

        response = self.client.get(
            f"/api/v1/maintenance/devices/{deviceId}/report", {"export": "csv"}, **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertUsableAttachmentHeader(
            response["Content-Disposition"], f"maintenance-report-{PERSIAN_CODE}.csv"
        )

    def testHandWrittenHeaderWouldHaveFailed(self) -> None:
        """Documents why the helper is required rather than a nicety."""
        from django.http import HttpResponse

        naive = HttpResponse(b"x")
        naive["Content-Disposition"] = f'attachment; filename="report-{PERSIAN_CODE}.csv"'
        self.assertTrue(
            naive["Content-Disposition"].startswith("=?"),
            "Django no longer mangles the header; this guard can be removed.",
        )

        correct = content_disposition_header(True, f"report-{PERSIAN_CODE}.csv")
        assert correct is not None
        self.assertTrue(correct.startswith("attachment"))
