# Signed release verification

A signed release candidate is built from a clean tagged checkout; uncommitted source changes invalidate the relationship between the tag and artifact.

Release provenance names the exact builder workflow and source commit, allowing the verifier to compare the artifact with the repository's accepted build identity.

The release verifier checks the signature against the expected project identity, not merely whether any cryptographically valid signature exists.

The source archive and installed wheel must expose the same runtime version as the release tag before publication can proceed.

An isolated release smoke test installs the built wheel without the checkout on the import path to detect missing packaged modules.

A release containing a schema change includes a migration rehearsal and rollback evidence before the publication job receives permission to upload.

The dependency inventory is generated from the resolved build environment and distinguishes bundled components from optional runtime integrations.

When signature verification cannot reach a trust service, the release stays unverified; the pipeline does not silently treat the artifact as trusted.

A compromised release is withdrawn from the recommended installation path while its advisory preserves artifact hashes for operators investigating exposure.

The publication credential is available only to the final upload job after tests and artifact verification have succeeded.

