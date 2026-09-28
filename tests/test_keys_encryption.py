import os
import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key

ENV = ("VERIGATE_KEY_PASSPHRASE", "VERIGATE_REQUIRE_ENCRYPTED_KEY")


class KeyEncryptionTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in ENV}
        self.tmp = tempfile.TemporaryDirectory()
        self.priv = Path(self.tmp.name) / "issuer.key"
        self.pub = Path(self.tmp.name) / "issuer.pub"

    def tearDown(self):
        self.tmp.cleanup()
        for k, v in self._saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    def test_plaintext_default_still_works(self):
        generate_keypair(self.priv, self.pub)
        self.assertIn(b"BEGIN PRIVATE KEY", self.priv.read_bytes())
        load_private_key(self.priv)

    def test_passphrase_encrypts_at_rest_and_roundtrips(self):
        generate_keypair(self.priv, self.pub, passphrase=b"correct horse battery")
        self.assertIn(b"ENCRYPTED PRIVATE KEY", self.priv.read_bytes())
        key = load_private_key(self.priv, passphrase=b"correct horse battery")
        self.assertEqual(
            key.public_key().public_bytes_raw(),
            load_public_key(self.pub).public_bytes_raw(),
        )

    def test_env_passphrase_used_for_generate_and_load(self):
        os.environ["VERIGATE_KEY_PASSPHRASE"] = "env-passphrase-123"
        generate_keypair(self.priv, self.pub)
        self.assertIn(b"ENCRYPTED PRIVATE KEY", self.priv.read_bytes())
        load_private_key(self.priv)

    def test_wrong_or_missing_passphrase_fails(self):
        generate_keypair(self.priv, self.pub, passphrase=b"right-passphrase")
        with self.assertRaises(ValueError):
            load_private_key(self.priv, passphrase=b"wrong-passphrase")
        with self.assertRaises(ValueError):
            load_private_key(self.priv)

    def test_require_encrypted_refuses_plaintext_generate_and_load(self):
        generate_keypair(self.priv, self.pub)  # plaintext file exists
        os.environ["VERIGATE_REQUIRE_ENCRYPTED_KEY"] = "1"
        with self.assertRaises(ValueError):
            load_private_key(self.priv)
        with self.assertRaises(RuntimeError):
            generate_keypair(Path(self.tmp.name) / "b.key", Path(self.tmp.name) / "b.pub")

    def test_cache_does_not_hide_a_replaced_key_file(self):
        generate_keypair(self.priv, self.pub)
        first = load_private_key(self.priv).public_key().public_bytes_raw()
        generate_keypair(self.priv, self.pub)
        second = load_private_key(self.priv).public_key().public_bytes_raw()
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
