import unittest

from demo_live_solana_devnet import (
    EXPECTED_DEVNET_GENESIS_HASH,
    b58decode,
    b58encode,
    require_devnet_cluster,
)


class SolanaDemoBase58Tests(unittest.TestCase):
    def test_devnet_cluster_guard_accepts_expected_genesis_hash(self):
        class Rpc:
            def get_genesis_hash(self):
                return EXPECTED_DEVNET_GENESIS_HASH

        self.assertEqual(require_devnet_cluster(Rpc()), EXPECTED_DEVNET_GENESIS_HASH)

    def test_devnet_cluster_guard_rejects_wrong_genesis_hash(self):
        class Rpc:
            def get_genesis_hash(self):
                return "not-devnet"

        with self.assertRaisesRegex(RuntimeError, "genesis hash mismatch"):
            require_devnet_cluster(Rpc())

    def test_round_trip_preserves_leading_zero_bytes(self):
        for raw in (bytes(32), b"\x00\x00\x01", bytes(range(32)), bytes([0xFF]) * 32):
            with self.subTest(raw=raw.hex()):
                self.assertEqual(b58decode(b58encode(raw)), raw)

    def test_system_program_zero_key_has_canonical_address(self):
        self.assertEqual(b58encode(bytes(32)), "1" * 32)
        self.assertEqual(b58decode("1" * 32), bytes(32))


if __name__ == "__main__":
    unittest.main()
