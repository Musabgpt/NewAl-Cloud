# MusabAI Android signing continuity

Phase 9 requires a persistent Android signing identity for every publishable APK.

## Why this exists

Phase 8 Action #304 and Phase 9 Action #306 were both built with Android debug signing, but their certificate SHA256 fingerprints were different because separate GitHub-hosted runners generated different debug keystores. An APK signed by a different certificate cannot update an already installed APK in place.

The private signing key cannot be recovered from an APK certificate.

## Persistent release identity

The publishable workflow expects all of these GitHub Actions Secrets together:

- `MUSABAI_RELEASE_KEYSTORE_B64`
- `MUSABAI_RELEASE_STORE_PASSWORD`
- `MUSABAI_RELEASE_KEY_ALIAS`
- `MUSABAI_RELEASE_KEY_PASSWORD`
- `MUSABAI_RELEASE_CERT_SHA256`

The keystore must be generated and backed up outside the repository. Store only its base64 representation in the GitHub Secret. Store passwords and alias values only as Secrets. The certificate SHA256 fingerprint is public information, but it is kept in the same protected configuration set so the workflow can reject accidental identity changes.

The workflow materializes the keystore only under `RUNNER_TEMP`, uses a restrictive umask, never enables shell tracing, passes passwords through environment variables rather than command-line arguments, verifies the APK with `apksigner`, compares the extracted certificate SHA256 fingerprint with the approved value, and deletes the temporary keystore before the build step exits.

## CI policy

A publishable `MusabAI-Connectors` artifact is uploaded only when all persistent release-signing values are present and the certificate fingerprint matches the approved fingerprint.

If no release-signing Secrets are configured, CI may still build `MusabAI-Connectors-Development` using an explicitly opted-in debug identity. That artifact is development-only and is not an update-signing baseline.

If only some signing Secrets are configured, or if the APK certificate fingerprint differs from the approved value, CI fails.

Tracked `.jks`, `.keystore`, `.p12`, `.pfx`, `keystore.properties`, `signing.properties`, and PEM private-key material are rejected by CI.

## Local builds

Without release-signing environment variables, the release variant is unsigned by default. A local developer can opt into a debug-signed release-shaped APK with:

`MUSABAI_ALLOW_DEBUG_SIGNING=true`

That opt-in build is for development only and must not be distributed as the MusabAI update baseline.

## One-time migration

Unless the private key used by Phase 8 Action #304 is found in an existing secure secret store, the first APK built with the new persistent release identity cannot update #304 in place. Devices with #304 installed need one uninstall/reinstall migration to the new persistent baseline. After that migration, future APKs can update in place as long as the same persistent signing key is retained and the CI fingerprint gate remains unchanged.

Keep at least two encrypted backups of the release keystore in separate secure locations. Losing the private key permanently breaks update continuity for installs signed by it.
