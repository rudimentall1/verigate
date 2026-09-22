import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_public_key
from core.storage import Storage
from enforcement.evm import EVMExecutionAdapter
from enforcement.networks import NetworkRegistry, UnsupportedNetworkError
from enforcement.solana import SolanaExecutionAdapter


class NetworkRegistryTest(unittest.TestCase):
    def test_known_evm_networks_share_universal_adapter(self):
        registry = NetworkRegistry()
        expected = {
            "ethereum": 1, "base": 8453, "arbitrum": 42161, "optimism": 10,
            "polygon": 137, "bnb-smart-chain": 56, "avalanche": 43114,
            "linea": 59144, "zksync-era": 324, "arc": 5042,
        }
        self.assertEqual({name: registry.resolve(name).chain_id for name in expected}, expected)
        with tempfile.TemporaryDirectory() as td:
            private = Path(td) / "issuer.key"
            public = Path(td) / "issuer.pub"
            generate_keypair(private, public)
            storage = Storage(Path(td) / "audit.db")
            try:
                for name in expected:
                    self.assertIsInstance(
                        registry.adapter(name, storage, load_public_key(public)),
                        EVMExecutionAdapter,
                    )
            finally:
                storage.close()

    def test_any_unlisted_evm_chain_can_use_universal_adapter(self):
        descriptor = NetworkRegistry().resolve_evm_chain(999999, name="my-evm")
        self.assertEqual(descriptor.family, "evm")
        self.assertEqual(descriptor.chain_id, 999999)
        self.assertTrue(descriptor.execution_supported)

    def test_unknown_named_network_fails_closed(self):
        with self.assertRaises(UnsupportedNetworkError):
            NetworkRegistry().resolve("some-new-chain")

    def test_solana_has_real_execution_adapter(self):
        registry = NetworkRegistry()
        self.assertEqual(registry.resolve("solana").family, "solana")
        with tempfile.TemporaryDirectory() as td:
            private = Path(td) / "issuer.key"
            public = Path(td) / "issuer.pub"
            generate_keypair(private, public)
            storage = Storage(Path(td) / "audit.db")
            try:
                self.assertIsInstance(
                    registry.adapter("solana", storage, load_public_key(public)),
                    SolanaExecutionAdapter,
                )
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
