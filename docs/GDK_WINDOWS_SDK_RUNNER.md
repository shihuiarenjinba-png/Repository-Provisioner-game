# Signal Sprint — guarded local Windows GDK SDK execution

Partner Center selection: **GDK game**. Route GDK_GAME / MSIXVC2, not ordinary app MSIX/PWA.

The check-only CLI gdk_windows_sdk_runner.py bridges the existing immutable Factory/Provisioner dual gate and a future real Windows makepkg.exe pack /msixvc2 execution. It never logs in to Partner Center, retrieves Identity, performs CAS, rebuilds SignalSprint.exe, installs a package, changes Windows security policy, uploads to Store, or modifies the Windows-all-auto central ledger.

## Preconditions

1. Factory source branch remains at c058cbf7fe38e02d929c67d047d717ff74bd522e; actual CAS and dedicated GDK build branch must be independently verified. Never use placeholder CAS SHA values.
2. The pinned ZIP/EXE are unchanged. The SDK handoff SHA-256 must be supplied through a separate trusted channel, not from the same handoff folder.
3. The reviewed reserved display name and package version are available. Neither is inferred from the Identity Name.
4. On an authorized Windows machine, the installed GDK's makepkg.exe is discoverable via PATH, GameDK/bin, GameDKCoreLatest/bin, GDK_BIN, or Program Files (x86)/Microsoft GDK/bin. Multiple distinct candidates cause HOLD; select one with --makepkg-path. Current-directory and relative PATH hits are not eligible; all explicit makepkg paths and GDK environment roots must be absolute. SDK discovery must never trust Windows current-directory command lookup. Its SHA-256 MUST be independently approved. Discovery is never approval. The SDK version string is a claim, not independent validation.
5. Output directory is empty and isolated. SDK log and result-evidence destinations do not exist and are outside Factory/staging/output. Use fresh paths for retries. Never reuse partially failed output.

## Check-only first

Run gdk_windows_sdk_runner.py with the following arguments, using actual independently reviewed values:

- --factory-checkout PATH_TO_DEDICATED_POST_CAS_FACTORY_BUILD
- --pinned-artifact-zip PATH_TO_FIXED_ARTIFACT
- --cas-commit-sha ACTUAL_CAS_SHA
- --build-head-sha ACTUAL_BUILD_SHA
- --factory-gate-script PATH_TO_INDEPENDENTLY_REVIEWED_GATE
- --trusted-factory-gate-sha256 APPROVED_FACTORY_GATE_SHA256
- --staging-dir PATH_TO_VERIFIED_GDK_STAGING
- --package-version REVIEWED_PACKAGE_VERSION
- --reviewed-display-name REVIEWED_RESERVED_DISPLAY_NAME
- --preflight-receipt PATH_TO_PREFLIGHT_JSON
- --output-dir EMPTY_ISOLATED_GDK_OUTPUT_DIR
- --sdk-handoff PATH_TO_SDK_HANDOFF_JSON
- --trusted-handoff-sha256 INDEPENDENTLY_APPROVED_HANDOFF_SHA256
- --pack-plan PATH_TO_PACK_PLAN_JSON
- --sdk-version-claim REVIEWED_INSTALLED_GDK_VERSION
- --validation-log NEW_PATH_OUTSIDE_OUTPUT_FOR_SDK_LOG
- --result-evidence NEW_PATH_OUTSIDE_OUTPUT_FOR_SDK_RESULT_JSON

A successful check-only response is GDK_WINDOWS_SDK_EXECUTION_CHECK_ONLY_READY. It does not create a package or approve anything.

Only on a reviewed Windows machine, repeat with --execute and --trusted-makepkg-sha256 INDEPENDENTLY_APPROVED_MAKEPKG_EXE_SHA256. If multiple installed SDK versions are detected, add --makepkg-path PATH_TO_REVIEWED_MAKEPKG_EXE; this path is still checked against the independent SHA-256. No SDK is installed, downloaded, or executed during check-only. The script re-derives the dual gate and pack plan, hashes the executable, invokes the exact reviewed argument vector without a shell, records SDK output, rechecks Factory/staging, and emits strict SDK result evidence only after byte verification. Failures do not produce a trusted success receipt; any output left from unsuccessful execution is untrusted and must not be consumed.

GDK_WINDOWS_SDK_OUTPUT_INTAKE_CHECK_PASS attests only to local bytes and a claimed SDK exit code. real_msix_pass, e2e_pass, gdk_sdk_validation_independently_verified, and store_submitted remain false. Next owners must independently run gdk_sdk_trusted_intake.py, gdk_e2e_trusted_export.py, Windows install/GUI QA, and Store gates.

tests/test_gdk_windows_sdk_runner.py uses synthetic SDK output and a mocked executable; it never calls real GDK or Partner Center. This PR cannot count as REAL_MSIX_PASS without actual Windows SDK evidence.


Discovery unit tests: tests/test_gdk_sdk_discovery.py. These exercise PATH-independent roots, ambiguity, explicit selection, and unsafe linked candidates without a real GDK.
