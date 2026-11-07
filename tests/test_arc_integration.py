import json
import unittest
from decimal import Decimal

from enforcement.evm_rpc import EvmRpcClient
from integrations.arc import (
    ARC_CHAIN_ID,
    ARC_USDC_ADDRESS,
    ARC_USDC_ERC20_DECIMALS,
    ArcIntegrationError,
    ArcMainnetIntegration,
    arc_payment_metadata,
    build_usdc_transfer_calldata,
    build_usdc_transfer_transaction,
    usdc_to_base_units,
    validate_arc_usdc_transfer,
)


SENDER = "0x1111111111111111111111111111111111111111"
RECIPIENT = "0x2222222222222222222222222222222222222222"


class ArcPaymentEncodingTest(unittest.TestCase):
    def test_transfer_calldata_uses_six_decimal_erc20_units(self):
        data = build_usdc_transfer_calldata(RECIPIENT, "1.234567")
        self.assertEqual(data[:10], "0xa9059cbb")
        self.assertEqual(data[10:74], RECIPIENT[2:].lower().rjust(64, "0"))
        self.assertEqual(int(data[74:], 16), 1_234_567)
        self.assertEqual(usdc_to_base_units(Decimal("2.5")), 2_500_000)

    def test_wallet_transaction_targets_arc_usdc_on_chain_5042(self):
        tx = build_usdc_transfer_transaction(SENDER, RECIPIENT, "5")
        self.assertEqual(tx["chain_id"], ARC_CHAIN_ID)
        self.assertEqual(tx["from"], SENDER)
        self.assertEqual(tx["to"], ARC_USDC_ADDRESS)
        self.assertEqual(tx["value_wei"], 0)
        self.assertEqual(tx["data"], build_usdc_transfer_calldata(RECIPIENT, "5"))

    def test_payment_metadata_is_explicitly_evm_and_arc(self):
        metadata = arc_payment_metadata(SENDER, RECIPIENT, "1")
        self.assertEqual(metadata["network_family"], "evm")
        self.assertEqual(metadata["evm_transaction"]["chain_id"], ARC_CHAIN_ID)
        self.assertEqual(metadata["arc"]["token_decimals"], ARC_USDC_ERC20_DECIMALS)

    def test_transaction_validator_rejects_recipient_or_amount_tampering(self):
        tx = build_usdc_transfer_transaction(SENDER, RECIPIENT, "1")
        validate_arc_usdc_transfer(tx, sender=SENDER, recipient=RECIPIENT, amount="1")
        changed = dict(tx)
        changed["data"] = build_usdc_transfer_calldata(SENDER, "1")
        with self.assertRaises(ArcIntegrationError):
            validate_arc_usdc_transfer(changed, sender=SENDER, recipient=RECIPIENT, amount="1")

    def test_invalid_addresses_and_excess_precision_are_rejected(self):
        with self.assertRaises(ArcIntegrationError):
            build_usdc_transfer_calldata("not-an-address", "1")
        with self.assertRaises(ArcIntegrationError):
            build_usdc_transfer_calldata(RECIPIENT, "0.0000001")


class ArcMainnetStatusTest(unittest.TestCase):
    def _client(self, values):
        def transport(endpoint, payload, headers, timeout):
            request = json.loads(payload)
            result = values[request["method"]]
            return json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode()
        return EvmRpcClient("https://rpc.mainnet.arc.io", transport=transport)

    def test_status_verifies_chain_token_code_and_decimals(self):
        rpc = self._client({
            "eth_chainId": "0x13b2",
            "eth_blockNumber": "0x100",
            "eth_gasPrice": "0x2386f26fc10000",
            "eth_getCode": "0x60006000",
            "eth_call": "0x6",
        })
        result = ArcMainnetIntegration(rpc=rpc).status()
        self.assertTrue(result["verified"])
        self.assertEqual(result["chain_id"], 5042)
        self.assertEqual(result["usdc_erc20_decimals"], 6)
        self.assertEqual(result["native_gas_decimals"], 18)
        self.assertEqual(result["block_number"], 256)

    def test_status_rejects_wrong_chain(self):
        rpc = self._client({
            "eth_chainId": "0x1",
            "eth_blockNumber": "0x100",
            "eth_gasPrice": "0x1",
            "eth_getCode": "0x6000",
            "eth_call": "0x6",
        })
        with self.assertRaises(ArcIntegrationError):
            ArcMainnetIntegration(rpc=rpc).status()

    def test_status_rejects_wrong_usdc_decimals(self):
        rpc = self._client({
            "eth_chainId": "0x13b2",
            "eth_blockNumber": "0x100",
            "eth_gasPrice": "0x1",
            "eth_getCode": "0x6000",
            "eth_call": "0x12",
        })
        with self.assertRaises(ArcIntegrationError):
            ArcMainnetIntegration(rpc=rpc).status()


if __name__ == "__main__":
    unittest.main()
