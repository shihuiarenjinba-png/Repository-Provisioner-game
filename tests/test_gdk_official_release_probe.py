"""Offline tests: never contact GitHub or install an SDK."""
import json
import unittest

import gdk_official_release_probe as release_probe


def feed(*items):
    return json.dumps(list(items)).encode("utf-8")


def item(tag, draft=False, prerelease=False):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease}


class OfficialGdkReleaseProbeTests(unittest.TestCase):
    def test_retail_tag_is_only_unapproved_candidate(self):
        result = release_probe.probe(lambda: feed(
            item("April-2026-Update-5-v2604.5.7903"),
            item("October-2026-v2610.0.8100"),
            item("October-2026-Update-1-v2610.1.8120")))
        self.assertEqual(result["catalog_status"], "OFFICIAL_2610_TAG_CANDIDATE_UNAPPROVED")
        self.assertEqual(len(result["observed_2610_release_tags_unapproved"]), 2)
        self.assertFalse(result["sdk_approved"])
        self.assertFalse(result["makepkg_sha256_approved"])
        self.assertFalse(result["real_msix_pass"])

    def test_preview_draft_and_unrelated_tags_not_retail(self):
        result = release_probe.probe(lambda: feed(
            item("October-2026-v2610.0.8100", draft=True),
            item("October-2026-Update-1-v2610.1.8120", prerelease=True),
            item("RIT-2610-v0.0.13-preview"),
            item("April-2026-Update-5-v2604.5.7903")))
        self.assertEqual(result["catalog_status"], "NO_2610_TAG_ON_OBSERVED_PAGE")
        self.assertEqual(result["observed_2610_release_tags_unapproved"], [])
        self.assertFalse(result["catalog_exhaustive"])

    def test_full_first_page_never_proves_absence(self):
        result = release_probe.probe(lambda: feed(*[
            item(f"April-2026-Update-{i}-v2604.{i}.7903") for i in range(100)]))
        self.assertEqual(result["catalog_status"], "UNKNOWN_FIRST_PAGE_FULL")
        self.assertFalse(result["catalog_exhaustive"])

    def test_network_error_is_unknown_not_no_release(self):
        def unavailable():
            raise OSError("rate limited")
        result = release_probe.probe(unavailable)
        self.assertEqual(result["catalog_status"], "UNKNOWN_QUERY_FAILED_OR_UNTRUSTED")
        self.assertFalse(result["sdk_installed"])

    def test_ambiguous_json_is_unknown(self):
        result = release_probe.probe(lambda: b'[{"tag_name":"a","tag_name":"b"}]')
        self.assertEqual(result["catalog_status"], "UNKNOWN_QUERY_FAILED_OR_UNTRUSTED")

    def test_untrusted_schema_is_unknown(self):
        for payload in (b'{}', b'[null]', b'not json', b'[]' * 100):
            with self.subTest(payload=payload[:10]):
                result = release_probe.probe(lambda p=payload: p)
                if payload == b'[]' * 100:
                    self.assertEqual(result["catalog_status"], "UNKNOWN_QUERY_FAILED_OR_UNTRUSTED")
                elif payload == b'{}' or payload == b'[null]' or payload == b'not json':
                    self.assertEqual(result["catalog_status"], "UNKNOWN_QUERY_FAILED_OR_UNTRUSTED")

    def test_never_claims_downstream_success(self):
        result = release_probe.probe(lambda: feed(item("October-2026-v2610.0.8100")))
        self.assertEqual(result["partner_center_selection"], "GDK_GAME")
        self.assertEqual(result["immutable_source_sha"], release_probe.SOURCE_SHA)
        for flag in ("sdk_installed", "sdk_approved", "makepkg_executed",
                     "makepkg_sha256_approved", "cas_return_pass", "real_msix_pass",
                     "e2e_pass", "store_submitted"):
            self.assertIs(result[flag], False, flag)


if __name__ == "__main__":
    unittest.main()
