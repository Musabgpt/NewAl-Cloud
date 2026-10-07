import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GRADLE = (ROOT / "android-lite/app/build.gradle.kts").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/android.yml").read_text(encoding="utf-8")
GITIGNORE = (ROOT / ".gitignore").read_text(encoding="utf-8")


class SigningPolicyTests(unittest.TestCase):
    def test_release_signing_comes_from_environment_and_debug_is_opt_in(self):
        for name in (
            "MUSABAI_RELEASE_STORE_FILE",
            "MUSABAI_RELEASE_STORE_PASSWORD",
            "MUSABAI_RELEASE_KEY_ALIAS",
            "MUSABAI_RELEASE_KEY_PASSWORD",
        ):
            self.assertIn(name, GRADLE)
        self.assertIn('allowDebugSigning -> signingConfigs.getByName("debug")', GRADLE)
        self.assertIn("else -> null", GRADLE)
        self.assertNotIn(
            'signingConfig = signingConfigs.getByName("debug")',
            GRADLE,
        )

    def test_release_workflow_requires_complete_persistent_identity(self):
        for name in (
            "MUSABAI_RELEASE_KEYSTORE_B64",
            "MUSABAI_RELEASE_STORE_PASSWORD",
            "MUSABAI_RELEASE_KEY_ALIAS",
            "MUSABAI_RELEASE_KEY_PASSWORD",
            "MUSABAI_RELEASE_CERT_SHA256",
        ):
            self.assertIn(name, WORKFLOW)
        self.assertIn("Persistent release signing configuration is incomplete", WORKFLOW)

    def test_apksigner_and_fingerprint_gate_are_mandatory_for_release_artifact(self):
        self.assertIn('verify --verbose --print-certs MusabAI-Connectors.apk', WORKFLOW)
        self.assertIn('if [ "$actual" != "$expected" ]', WORKFLOW)
        self.assertIn("APK signing identity does not match the approved persistent fingerprint", WORKFLOW)

    def test_keystore_is_materialized_only_in_runner_temp_and_cleaned(self):
        self.assertIn('KEYSTORE_FILE="$RUNNER_TEMP/musabai-release.jks"', WORKFLOW)
        self.assertIn("base64 --decode", WORKFLOW)
        self.assertIn('rm -f "$KEYSTORE_FILE"', WORKFLOW)
        self.assertNotIn("set -x", WORKFLOW)

    def test_missing_release_identity_produces_only_development_named_apk(self):
        self.assertIn("MusabAI-Connectors-DEV.apk", WORKFLOW)
        self.assertIn("MusabAI-Connectors-Development", WORKFLOW)
        self.assertIn("Development APK only", WORKFLOW)

    def test_repository_history_is_scanned_for_signing_material(self):
        self.assertIn("fetch-depth: 0", WORKFLOW)
        self.assertIn("git log --all --name-only", WORKFLOW)
        self.assertIn("git rev-list --all", WORKFLOW)
        self.assertIn("Private-key text exists in reachable Git history", WORKFLOW)

    def test_signing_material_patterns_are_ignored(self):
        for pattern in (
            "*.jks",
            "*.keystore",
            "*.p12",
            "*.pfx",
            "keystore.properties",
            "signing.properties",
        ):
            self.assertIn(pattern, GITIGNORE)


if __name__ == "__main__":
    unittest.main()
