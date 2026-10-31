"""Offline tests for read-only GDK component discovery; no network or install."""
import json
import unittest

import gdk_nuget_component_probe as nuget


def feed(*versions):
    return json.dumps({"versions": list(versions)}).encode()


class NugetGdkComponentProbeTests(unittest.TestCase):
    def test_2610_is_only_unapproved_component_candidate(self):
        r = nuget.probe(lambda: feed("2604.5.7903", "2610.0.8000", "2610.1.8001"))
        self.assertEqual(r["component_catalog_status"], "2610_COMPONENT_VERSION_CANDIDATE_UNAPPROVED")
        self.assertEqual(r["observed_2610_component_versions_unapproved"], ["2610.0.8000", "2610.1.8001"])
        for key in ("complete_gdk_sdk_available", "sdk_installed", "sdk_approved",
                    "makepkg_sha256_approved", "cas_return_pass", "real_msix_pass",
                    "e2e_pass", "store_submitted"):
            self.assertIs(r[key], False, key)

    def test_preview_or_other_component_versions_not_retail_candidate(self):
        r = nuget.probe(lambda: feed("2604.5.7903", "2610.0.8100-preview", "2510.5.6322"))
        self.assertEqual(r["component_catalog_status"], "NO_2610_COMPONENT_VERSION_OBSERVED")
        self.assertEqual(r["observed_2610_component_versions_unapproved"], [])

    def test_catalog_failure_or_invalid_schema_is_unknown(self):
        samples = [b"", b"{}", b'{"versions":[]}', b'{"versions":[null]}',
                   b'{"versions":["2610.0.8000"],"versions":["2604.5.7903"]}',
                   b'{"versions":["2610.0.8000"],"unexpected":true}',
                   b'{"versions":[NaN]}', b"not json"]
        for raw in samples:
            with self.subTest(raw=raw[:30]):
                self.assertEqual(nuget.probe(lambda raw=raw: raw)["component_catalog_status"],
                                 "UNKNOWN_QUERY_FAILED_OR_UNTRUSTED")
        def fail():
            raise OSError("network unavailable")
        self.assertEqual(nuget.probe(fail)["component_catalog_status"],
                         "UNKNOWN_QUERY_FAILED_OR_UNTRUSTED")

    def test_bounded_output_and_no_false_approval(self):
        r = nuget.probe(lambda: feed(*(f"2610.{i}.8000" for i in range(70))))
        self.assertEqual(len(r["observed_2610_component_versions_unapproved"]), 50)
        self.assertEqual(r["observed_2610_component_versions_unapproved"][-1], "2610.69.8000")
        self.assertEqual(r["immutable_source_sha"], nuget.SOURCE_SHA)
        self.assertEqual(r["partner_center_selection"], "GDK_GAME")


if __name__ == "__main__":
    unittest.main()
