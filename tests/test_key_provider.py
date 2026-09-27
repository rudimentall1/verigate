import os
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from attest.key_provider import (
    DerivedMultiTenantKeyProvider,
    LocalFileKeyProvider,
    TenantKeyDirectoryProvider,
)
from attest.keys import generate_keypair, load_private_key


def _priv_bytes(key: Ed25519PrivateKey) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


class TestLocalFileKeyProvider(unittest.TestCase):
    def test_matches_existing_single_tenant_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            priv = Path(tmp) / "issuer.key"
            pub = Path(tmp) / "issuer.pub"
            generate_keypair(priv, pub)

            provider = LocalFileKeyProvider(private_key_path=str(priv))
            key_via_provider = provider.get_private_key(tenant_id="ignored")
            key_direct = load_private_key(priv)

            self.assertEqual(_priv_bytes(key_via_provider), _priv_bytes(key_direct))


class TestTenantKeyDirectoryProvider(unittest.TestCase):
    def test_distinct_tenants_get_distinct_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = TenantKeyDirectoryProvider(base_dir=tmp)
            key_a = provider.get_private_key("tenant-a")
            key_b = provider.get_private_key("tenant-b")
            self.assertNotEqual(_priv_bytes(key_a), _priv_bytes(key_b))

    def test_key_persists_across_provider_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = TenantKeyDirectoryProvider(base_dir=tmp)
            key_first = first.get_private_key("tenant-a")

            second = TenantKeyDirectoryProvider(base_dir=tmp)
            key_second = second.get_private_key("tenant-a")

            self.assertEqual(_priv_bytes(key_first), _priv_bytes(key_second))

    def test_rejects_path_traversal_tenant_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = TenantKeyDirectoryProvider(base_dir=tmp)
            for bad in ["../escape", "a/b", "a\\b", "", ".."]:
                with self.assertRaises(ValueError):
                    provider.get_private_key(bad)

    def test_encryption_at_rest_key_file_is_not_plain_pem(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = TenantKeyDirectoryProvider(
                base_dir=tmp, encryption_passphrase=b"correct horse battery staple"
            )
            provider.get_private_key("tenant-a")
            raw = (Path(tmp) / "tenant-a" / "issuer.key").read_bytes()
            self.assertNotIn(b"BEGIN PRIVATE KEY", raw)

    def test_wrong_passphrase_fails_to_decrypt(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = TenantKeyDirectoryProvider(
                base_dir=tmp, encryption_passphrase=b"correct horse battery staple"
            )
            provider.get_private_key("tenant-a")

            wrong = TenantKeyDirectoryProvider(
                base_dir=tmp, encryption_passphrase=b"wrong passphrase entirely"
            )
            with self.assertRaises(ValueError):
                wrong.get_private_key("tenant-a")

    def test_encrypted_and_plaintext_providers_recover_same_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = TenantKeyDirectoryProvider(
                base_dir=tmp, encryption_passphrase=b"correct horse battery staple"
            )
            key_a = provider.get_private_key("tenant-a")

            # A fresh instance with the SAME passphrase must recover the
            # identical key from disk, not silently regenerate one.
            reopened = TenantKeyDirectoryProvider(
                base_dir=tmp, encryption_passphrase=b"correct horse battery staple"
            )
            key_a_again = reopened.get_private_key("tenant-a")
            self.assertEqual(_priv_bytes(key_a), _priv_bytes(key_a_again))


class TestDerivedMultiTenantKeyProvider(unittest.TestCase):
    def test_deterministic_per_tenant(self):
        provider = DerivedMultiTenantKeyProvider(master_secret=b"x" * 32)
        key_a1 = provider.get_private_key("tenant-a")
        key_a2 = provider.get_private_key("tenant-a")
        self.assertEqual(_priv_bytes(key_a1), _priv_bytes(key_a2))

    def test_distinct_across_tenants(self):
        provider = DerivedMultiTenantKeyProvider(master_secret=b"x" * 32)
        key_a = provider.get_private_key("tenant-a")
        key_b = provider.get_private_key("tenant-b")
        self.assertNotEqual(_priv_bytes(key_a), _priv_bytes(key_b))

    def test_rejects_short_master_secret(self):
        with self.assertRaises(ValueError):
            DerivedMultiTenantKeyProvider(master_secret=b"too-short")

    def test_rejects_path_traversal_tenant_id(self):
        provider = DerivedMultiTenantKeyProvider(master_secret=b"x" * 32)
        with self.assertRaises(ValueError):
            provider.get_private_key("../escape")

    def test_from_env_round_trip_plain_passphrase(self):
        os.environ["VERIGATE_TENANT_MASTER_SECRET"] = "a fairly long passphrase, 32+ chars!!"
        try:
            provider = DerivedMultiTenantKeyProvider.from_env()
            key = provider.get_private_key("tenant-a")
            self.assertIsInstance(key, Ed25519PrivateKey)
        finally:
            del os.environ["VERIGATE_TENANT_MASTER_SECRET"]

    def test_from_env_round_trip_base64_prefix(self):
        import base64
        import secrets

        encoded = base64.b64encode(secrets.token_bytes(32)).decode()
        os.environ["VERIGATE_TENANT_MASTER_SECRET"] = f"base64:{encoded}"
        try:
            provider = DerivedMultiTenantKeyProvider.from_env()
            key = provider.get_private_key("tenant-a")
            self.assertIsInstance(key, Ed25519PrivateKey)
        finally:
            del os.environ["VERIGATE_TENANT_MASTER_SECRET"]

    def test_from_env_plain_passphrase_that_also_looks_like_base64_is_not_mis_truncated(self):
        # Regression: a 32-char passphrase made only of base64-alphabet
        # characters must NOT be silently base64-decoded (which would
        # shrink it to 24 bytes and could wrongly raise "too short", or
        # worse, silently derive keys from a truncated secret).
        os.environ["VERIGATE_TENANT_MASTER_SECRET"] = "y" * 32
        try:
            provider = DerivedMultiTenantKeyProvider.from_env()
            self.assertEqual(len(provider.master_secret), 32)
        finally:
            del os.environ["VERIGATE_TENANT_MASTER_SECRET"]

    def test_from_env_missing_raises(self):
        os.environ.pop("VERIGATE_TENANT_MASTER_SECRET", None)
        with self.assertRaises(RuntimeError):
            DerivedMultiTenantKeyProvider.from_env()


if __name__ == "__main__":
    unittest.main()
