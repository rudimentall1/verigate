"""Regression tests for Ed25519 issuer key file permissions."""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from attest.keys import ensure_keypair, generate_keypair, load_private_key, load_public_key


@unittest.skipUnless(os.name == "posix", "POSIX file modes are not portable")
class IssuerKeyPermissionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="verigate-key-permissions-")
        self.directory = Path(self.tmp.name) / "issuer"
        self.private_path = self.directory / "issuer.key"
        self.public_path = self.directory / "issuer.pub"

    def tearDown(self):
        self.tmp.cleanup()

    def test_generated_keypair_uses_restrictive_modes(self):
        generate_keypair(self.private_path, self.public_path)

        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.private_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.public_path.stat().st_mode), 0o644)
        self.assertIsNotNone(load_private_key(self.private_path))
        self.assertIsNotNone(load_public_key(self.public_path))

    def test_loading_existing_key_tightens_legacy_permissions(self):
        generate_keypair(self.private_path, self.public_path)
        os.chmod(self.directory, 0o755)
        os.chmod(self.private_path, 0o644)

        self.assertIsNotNone(load_private_key(self.private_path))

        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.private_path.stat().st_mode), 0o600)

    def test_encrypted_private_key_still_round_trips(self):
        generate_keypair(self.private_path, self.public_path, passphrase=b"test-passphrase")
        self.assertIsNotNone(load_private_key(self.private_path, passphrase=b"test-passphrase"))
        with self.assertRaises(ValueError):
            load_private_key(self.private_path, passphrase=b"wrong-passphrase")

    def test_private_key_symlink_is_rejected(self):
        generate_keypair(self.private_path, self.public_path)
        link = self.directory / "issuer-link.key"
        link.symlink_to(self.private_path)

        with self.assertRaises(PermissionError):
            load_private_key(link)


class IssuerKeypairIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="verigate-keypair-integrity-")
        self.directory = Path(self.tmp.name)
        self.private_path = self.directory / "issuer.key"
        self.public_path = self.directory / "issuer.pub"

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_pair_only_when_both_files_are_absent(self):
        key = ensure_keypair(self.private_path, self.public_path)
        self.assertEqual(
            key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ),
            load_public_key(self.public_path).public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ),
        )

    def test_private_without_public_fails_closed(self):
        generate_keypair(self.private_path, self.public_path)
        self.public_path.unlink()
        with self.assertRaisesRegex(RuntimeError, "incomplete issuer keypair"):
            ensure_keypair(self.private_path, self.public_path)

    def test_public_without_private_fails_closed(self):
        generate_keypair(self.private_path, self.public_path)
        self.private_path.unlink()
        with self.assertRaisesRegex(RuntimeError, "incomplete issuer keypair"):
            ensure_keypair(self.private_path, self.public_path)

    def test_mismatched_pair_fails_closed(self):
        generate_keypair(self.private_path, self.public_path)
        other_private = self.directory / "other.key"
        other_public = self.directory / "other.pub"
        generate_keypair(other_private, other_public)
        self.public_path.write_bytes(other_public.read_bytes())
        with self.assertRaisesRegex(RuntimeError, "do not match"):
            ensure_keypair(self.private_path, self.public_path)



if __name__ == "__main__":
    unittest.main()
