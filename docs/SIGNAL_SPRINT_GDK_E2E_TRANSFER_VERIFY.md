# Signal Sprint GDK — independent E2E transfer byte receiver

**Partner Center selection: GDK game.** Only the pinned Signal Sprint request
and user-provided Identity are accepted. This tool is owned by the GAME lane
as a receiver contract; the 36-minute Windows/E2E lane owns its central queue,
actual GDK SDK inspection, installation, gameplay and Store certification.

## Check transferred bytes before QA

After `gdk_e2e_handoff.py` has produced a folder, record the sender CLI's
`handoff_manifest_sha256` **outside the handoff directory** via an
independently trusted channel (such as a verified build record). Do not
obtain the digest from the received manifest or an untrusted sidecar.
After transfer, run from Repository-Provisioner-game:

```powershell
python gdk_e2e_handoff_verify.py --handoff-dir C:\\qa\\gdk\\handoff --expected-manifest-sha256 <trusted-64-character-sha256>
```

The receiver requires exactly `package.msixvc2`, `validation.log` and
`handoff.json`. It rejects extra files, symlinks, duplicate JSON keys,
unrecognized manifest fields, changed package/log hashes, incorrect size,
wrong immutable source/request/branch, wrong reviewed Store Identity,
malformed CAS/build SHAs, unsafe filenames and any false approval claim.
It re-hashes the transferred package and log, but **never modifies them**.

Successful output is `GDK_E2E_TRANSFER_BYTES_CHECK_PASS`, which means only
the transport bytes match the independently pinned sender manifest. It is not proof
that makepkg ran, that MicrosoftGame.config matches the package, or that
the package installs or meets Store requirements. These require independent
Windows/GDK validation. The receiver always returns
`gdk_sdk_validation_independently_verified=false`,
`real_msix_pass=false`, `e2e_pass=false` and `store_submitted=false`.

## Negative regression tests

```bash
python -m unittest discover -s tests -p 'test_gdk_e2e_handoff_verify.py' -v
```

All fixtures are synthetic. No CAS, GDK SDK, Windows security settings,
central E2E queue, Store submission, or source branch is touched.

The source SHA is permanently
`c058cbf7fe38e02d929c67d047d717ff74bd522e`.
The Identity is already user-provided, not awaiting Partner Center login.
