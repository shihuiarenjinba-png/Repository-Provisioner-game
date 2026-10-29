"""Offline-only hosted GDK bootstrap regression tests. Never install SDK."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import gdk_hosted_sdk_bootstrap as bootstrap
from package_identity_provisioner import ConflictError, HoldError


class HostedBootstrapTests(unittest.TestCase):
    def test_preview_only_catalog_is_not_retail_ready(self):
        result = bootstrap._catalog_assessment("CANDIDATES_FOUND",
                                               ["2604.5.7903", "2604.4.7897"])
        self.assertEqual(result["preview_2604_catalog_status"],
                         "CANDIDATE_UNAPPROVED")
        self.assertEqual(result["retail_2610_catalog_status"], "NOT_LISTED")
        self.assertEqual(result["unapproved_2610_candidates"], [])
        self.assertFalse(result["retail_msixvc2_sdk_approved"])

    def test_retail_candidate_never_implies_sdk_approval(self):
        result = bootstrap._catalog_assessment("CANDIDATES_FOUND",
                                               ["2604.5.7903", "2610.0.8000"])
        self.assertEqual(result["retail_2610_catalog_status"],
                         "CANDIDATE_UNAPPROVED")
        self.assertEqual(result["unapproved_2610_candidates"], ["2610.0.8000"])
        self.assertFalse(result["retail_msixvc2_sdk_approved"])

    def test_unavailable_catalog_is_unknown_not_absent(self):
        for status in ("FAILED", "UNAVAILABLE", "WINGET_UNAVAILABLE", "NOT_QUERIED"):
            with self.subTest(status=status):
                result = bootstrap._catalog_assessment(status, [])
                self.assertEqual(result["retail_2610_catalog_status"], "UNKNOWN")
                self.assertEqual(result["preview_2604_catalog_status"], "UNKNOWN")
                self.assertFalse(result["retail_msixvc2_sdk_approved"])

    def test_catalog_probe_extracts_only_unapproved_2610_candidates(self):
        sample = "Version\n2610.0.8000\n2604.0.7500\n2610.0.8000\n2610.1.8100\n"
        with mock.patch.object(bootstrap.subprocess, "run",
                               return_value=mock.Mock(returncode=0, stdout=sample)) as run:
            result = bootstrap._probe_versions(Path("C:/approved/winget.exe"))
        self.assertEqual(result["catalog_query_status"], "CANDIDATES_FOUND")
        self.assertEqual(result["unapproved_version_candidates"],
                         ["2604.0.7500", "2610.0.8000", "2610.1.8100"])
        self.assertEqual(result["unapproved_2610_candidates"],
                         ["2610.0.8000", "2610.1.8100"])
        command = run.call_args.args[0]
        self.assertEqual(command[1], "show")
        self.assertIn("--versions", command)
        self.assertNotIn("install", command)

    def test_catalog_failure_does_not_claim_version_approval(self):
        with mock.patch.object(bootstrap.subprocess, "run",
                               return_value=mock.Mock(returncode=1, stdout="2610.0.8000")):
            result = bootstrap._probe_versions(Path("C:/approved/winget.exe"))
        self.assertEqual(result["catalog_query_status"], "FAILED")
        self.assertEqual(result["unapproved_version_candidates"], [])

    def test_catalog_timeout_fails_closed_without_install(self):
        with mock.patch.object(bootstrap.subprocess, "run",
                               side_effect=bootstrap.subprocess.TimeoutExpired("winget", 90)):
            result = bootstrap._probe_versions(Path("C:/approved/winget.exe"))
        self.assertEqual(result["catalog_query_status"], "UNAVAILABLE")
        self.assertEqual(result["unapproved_version_candidates"], [])

    def test_windows_probe_versions_never_installs_sdk(self):
        with mock.patch.object(bootstrap.sys, "platform", "win32"), \
             mock.patch.object(bootstrap, "_winget", return_value=Path("C:/approved/winget.exe")), \
             mock.patch.object(bootstrap, "_probe_versions",
                               return_value={"catalog_query_status": "CANDIDATES_FOUND",
                                             "unapproved_version_candidates": ["2610.0.8000"]}) as query:
            result = bootstrap.bootstrap(probe_versions=True)
        query.assert_called_once()
        self.assertEqual(result["status"], "GDK_HOSTED_WINGET_PROBE_ONLY")
        self.assertFalse(result["sdk_installed_by_this_run"])
        self.assertFalse(result["real_msix_pass"])
        self.assertEqual(result["unapproved_version_candidates"], ["2610.0.8000"])

    def test_missing_winget_catalog_probe_never_executes_subprocess(self):
        with mock.patch.object(bootstrap.sys, "platform", "win32"), \
             mock.patch.object(bootstrap, "_winget", return_value=None), \
             mock.patch.object(bootstrap.subprocess, "run") as run:
            result = bootstrap.bootstrap(probe_versions=True)
        self.assertEqual(result["catalog_query_status"], "WINGET_UNAVAILABLE")
        self.assertEqual(result["unapproved_version_candidates"], [])
        run.assert_not_called()

    def test_non_windows_probe_never_installs(self):
        with mock.patch.object(bootstrap.sys, "platform", "linux"):
            result = bootstrap.bootstrap()
        self.assertEqual(result["status"], "GDK_HOSTED_WINDOWS_REQUIRED")
        self.assertFalse(result["sdk_installed_by_this_run"])
        self.assertFalse(result["real_msix_pass"])

    def test_non_windows_install_rejected(self):
        with mock.patch.object(bootstrap.sys, "platform", "linux"):
            with self.assertRaisesRegex(HoldError, "Windows"):
                bootstrap.bootstrap(install=True)

    def test_windows_probe_no_winget_does_not_install(self):
        with mock.patch.object(bootstrap.sys, "platform", "win32"), \
             mock.patch.object(bootstrap, "_winget", return_value=None), \
             mock.patch.object(bootstrap.subprocess, "run") as run:
            result = bootstrap.bootstrap()
        self.assertEqual(result["status"], "GDK_HOSTED_WINGET_PROBE_ONLY")
        self.assertFalse(result["winget_available"])
        run.assert_not_called()

    def test_local_machine_install_forbidden_even_with_inputs(self):
        with mock.patch.object(bootstrap.sys, "platform", "win32"), \
             mock.patch.object(bootstrap, "_winget", return_value=Path("C:/winget.exe")), \
             mock.patch.dict(os.environ, {"CI": "true", "GITHUB_ACTIONS": "true",
                                          "RUNNER_OS": "Windows",
                                          "RUNNER_ENVIRONMENT": "self-hosted"}), \
             mock.patch.object(bootstrap.subprocess, "run") as run:
            with self.assertRaisesRegex(HoldError, "GitHub-hosted"):
                bootstrap.bootstrap(install=True, sdk_version="2610.0.8000",
                                    approved_makepkg_sha256="a" * 64)
        run.assert_not_called()

    def test_invalid_version_and_digest_rejected_before_install(self):
        env = {"CI": "true", "GITHUB_ACTIONS": "true",
               "RUNNER_OS": "Windows", "RUNNER_ENVIRONMENT": "github-hosted"}
        with mock.patch.object(bootstrap.sys, "platform", "win32"), \
             mock.patch.object(bootstrap, "_winget", return_value=Path("C:/winget.exe")), \
             mock.patch.dict(os.environ, env), \
             mock.patch.object(bootstrap.subprocess, "run") as run:
            for version, digest in (("2604.5.7903", "a" * 64),
                                    ("2610.0.8000;cmd", "a" * 64),
                                    ("2610.0.8000", "not-a-sha")):
                with self.subTest(version=version, digest=digest):
                    with self.assertRaises(HoldError):
                        bootstrap.bootstrap(install=True, sdk_version=version,
                                            approved_makepkg_sha256=digest)
        run.assert_not_called()

    def test_winget_failure_holds_without_approval(self):
        env = {"CI": "true", "GITHUB_ACTIONS": "true",
               "RUNNER_OS": "Windows", "RUNNER_ENVIRONMENT": "github-hosted"}
        with mock.patch.object(bootstrap.sys, "platform", "win32"), \
             mock.patch.object(bootstrap, "_winget", return_value=Path("C:/winget.exe")), \
             mock.patch.dict(os.environ, env), \
             mock.patch.object(bootstrap.subprocess, "run",
                               return_value=mock.Mock(returncode=1)) as run:
            with self.assertRaisesRegex(HoldError, "failed"):
                bootstrap.bootstrap(install=True, sdk_version="2610.0.8000",
                                    approved_makepkg_sha256="a" * 64)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], [str(Path("C:/winget.exe")), "install", "--id", "Microsoft.Gaming.GDK"])
        self.assertIn("--exact", command)
        self.assertNotIn("upload", command)

    def test_success_only_after_independent_executable_digest(self):
        env = {"CI": "true", "GITHUB_ACTIONS": "true",
               "RUNNER_OS": "Windows", "RUNNER_ENVIRONMENT": "github-hosted"}
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "makepkg.exe"
            exe.write_bytes(b"synthetic SDK - NEVER EXECUTED")
            expected = bootstrap._sha256(exe)
            with mock.patch.object(bootstrap.sys, "platform", "win32"), \
                 mock.patch.object(bootstrap, "_winget", return_value=Path("C:/winget.exe")), \
                 mock.patch.dict(os.environ, env), \
                 mock.patch.object(bootstrap.subprocess, "run",
                                   return_value=mock.Mock(returncode=0)), \
                 mock.patch.object(bootstrap, "discover_makepkg", return_value=exe):
                with self.assertRaisesRegex(ConflictError, "approved SHA"):
                    bootstrap.bootstrap(install=True, sdk_version="2610.0.8000",
                                        approved_makepkg_sha256="0" * 64)
                result = bootstrap.bootstrap(install=True, sdk_version="2610.0.8000",
                                             approved_makepkg_sha256=expected)
        self.assertEqual(result["status"], "GDK_HOSTED_SDK_BYTES_APPROVED_NO_BUILD")
        self.assertEqual(result["makepkg_sha256"], expected)
        self.assertFalse(result["makepkg_executed"])
        self.assertFalse(result["cas_return_pass"])
        self.assertFalse(result["real_msix_pass"])
        self.assertFalse(result["store_submitted"])

    def test_checkout_winget_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "winget.exe"
            candidate.write_bytes(b"untrusted")
            with mock.patch.dict(os.environ, {"GITHUB_WORKSPACE": temp, "PATH": temp}):
                with self.assertRaisesRegex(ConflictError, "checkout"):
                    bootstrap._winget()

    def test_cwd_winget_is_not_discovered(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "winget.exe").write_bytes(b"fake current-dir executable")
            with mock.patch.dict(os.environ, {"PATH": "", "GITHUB_WORKSPACE": ""}), \
                 mock.patch.object(bootstrap.Path, "cwd", return_value=Path(temp)):
                self.assertIsNone(bootstrap._winget())

    def test_relative_path_entry_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "winget.exe").write_bytes(b"fake executable")
            with mock.patch.dict(os.environ, {"PATH": ".", "GITHUB_WORKSPACE": ""}):
                self.assertIsNone(bootstrap._winget())

    def test_ambiguous_winget_candidates_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a", Path(temp) / "b"
            a.mkdir()
            b.mkdir()
            (a / "winget.exe").write_bytes(b"fake one")
            (b / "winget.exe").write_bytes(b"fake two")
            with mock.patch.dict(os.environ, {"PATH": f"{a};{b}", "GITHUB_WORKSPACE": ""}):
                with self.assertRaisesRegex(ConflictError, "multiple WinGet"):
                    bootstrap._winget()

    def test_absolute_path_winget_is_detected_without_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "winget.exe"
            candidate.write_bytes(b"synthetic executable")
            with mock.patch.dict(os.environ, {"PATH": temp, "GITHUB_WORKSPACE": ""}), \
                 mock.patch.object(bootstrap.subprocess, "run") as run:
                self.assertEqual(bootstrap._winget(), candidate)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
