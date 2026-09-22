import unittest

from enforcement.evm_rpc import EvmRpcClient
from enforcement.solana_rpc import SolanaRpcClient


class ConfirmationRpcTest(unittest.TestCase):
    def test_evm_pending_success_and_revert(self):
        responses = [
            b'{"jsonrpc":"2.0","id":1,"result":null}',
            b'{"jsonrpc":"2.0","id":1,"result":{"status":"0x1","blockNumber":"0x20","blockHash":"0xblock"}}',
            b'{"jsonrpc":"2.0","id":1,"result":{"status":"0x0","blockNumber":"0x21","blockHash":"0xrevert"}}',
        ]

        def transport(endpoint, payload, headers, timeout):
            return responses.pop(0)

        client = EvmRpcClient("https://example.invalid", transport=transport)
        self.assertEqual(client.confirm_transaction("0xabc")["state"], "PENDING")
        success = client.confirm_transaction("0xabc")
        self.assertEqual(success["state"], "CONFIRMED")
        self.assertEqual(success["block_ref"], "0x20")
        failed = client.confirm_transaction("0xdef")
        self.assertEqual(failed["state"], "FAILED")
        self.assertIn("reverted", failed["error"])

    def test_solana_pending_confirmed_and_failed(self):
        responses = [
            b'{"jsonrpc":"2.0","id":1,"result":{"value":[null]}}',
            b'{"jsonrpc":"2.0","id":1,"result":{"value":[{"slot":10,"confirmations":1,"confirmationStatus":"confirmed","err":null}]}}',
            b'{"jsonrpc":"2.0","id":1,"result":{"value":[{"slot":11,"confirmations":null,"confirmationStatus":"finalized","err":{"InstructionError":[0,"Custom"]}}]}}',
        ]

        def transport(endpoint, payload, headers, timeout):
            return responses.pop(0)

        client = SolanaRpcClient("https://example.invalid", transport=transport)
        self.assertEqual(client.confirm_transaction("sig")["state"], "PENDING")
        confirmed = client.confirm_transaction("sig")
        self.assertEqual(confirmed["state"], "CONFIRMED")
        self.assertEqual(confirmed["slot"], 10)
        failed = client.confirm_transaction("sig")
        self.assertEqual(failed["state"], "FAILED")
        self.assertIn("InstructionError", failed["error"])


if __name__ == "__main__":
    unittest.main()
