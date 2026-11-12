import unittest

from integrations.arc import (
    ARC_CHAIN_ID,
    ARC_USDC_ADDRESS,
    TRANSFER_EVENT_TOPIC,
    ArcPaymentSettlementVerifier,
    ArcPaymentVerificationError,
)


SENDER = "0x1111111111111111111111111111111111111111"
RECIPIENT = "0x2222222222222222222222222222222222222222"
PAYMENT_HASH = "0x" + "aa" * 32
CONSUME_HASH = "0x" + "bb" * 32
PAYMENT_BLOCK_HASH = "0x" + "cc" * 32
FINALIZED_BLOCK_HASH = "0x" + "dd" * 32
AMOUNT = 25_000_000


def address_topic(address):
    return "0x" + address[2:].rjust(64, "0")


def word(value):
    return format(value, "064x")


EXPECTED_DATA = "0xa9059cbb" + RECIPIENT[2:].rjust(64, "0") + word(AMOUNT)
EXPECTED_TRANSACTION = {
    "chain_id": ARC_CHAIN_ID,
    "from": SENDER,
    "to": ARC_USDC_ADDRESS,
    "value_wei": 0,
    "data": EXPECTED_DATA,
}


class FakeRpc:
    def __init__(self):
        self.payment_tx = {
            "hash": PAYMENT_HASH,
            "chainId": hex(ARC_CHAIN_ID),
            "from": SENDER,
            "to": ARC_USDC_ADDRESS,
            "input": EXPECTED_DATA,
            "value": "0x0",
            "blockNumber": "0x64",
            "transactionIndex": "0x2",
        }
        self.consumption_tx = {"hash": CONSUME_HASH}
        self.payment_receipt = {
            "transactionHash": PAYMENT_HASH,
            "status": "0x1",
            "from": SENDER,
            "to": ARC_USDC_ADDRESS,
            "blockNumber": "0x64",
            "blockHash": PAYMENT_BLOCK_HASH,
            "transactionIndex": "0x2",
            "logs": [{
                "address": ARC_USDC_ADDRESS,
                "topics": [
                    TRANSFER_EVENT_TOPIC,
                    address_topic(SENDER),
                    address_topic(RECIPIENT),
                ],
                "data": "0x" + word(AMOUNT),
                "logIndex": "0x0",
            }],
        }
        self.consumption_receipt = {
            "transactionHash": CONSUME_HASH,
            "status": "0x1",
            "blockNumber": "0x64",
            "blockHash": PAYMENT_BLOCK_HASH,
            "transactionIndex": "0x1",
        }
        self.finalized = {"number": "0x65", "hash": FINALIZED_BLOCK_HASH}

    def chain_id(self):
        return ARC_CHAIN_ID

    def get_transaction_by_hash(self, tx_hash):
        return self.payment_tx if tx_hash == PAYMENT_HASH else self.consumption_tx

    def get_transaction_receipt(self, tx_hash):
        return self.payment_receipt if tx_hash == PAYMENT_HASH else self.consumption_receipt

    def get_block_by_number(self, block_number):
        return {
            "number": hex(block_number),
            "hash": PAYMENT_BLOCK_HASH,
            "timestamp": "0x672f0000",
        }

    def get_block_by_tag(self, tag):
        return self.finalized


class ArcPaymentSettlementTests(unittest.TestCase):
    def setUp(self):
        self.rpc = FakeRpc()
        self.verifier = ArcPaymentSettlementVerifier(self.rpc)

    def confirm(self):
        return self.verifier.confirm_payment(
            expected_transaction=EXPECTED_TRANSACTION,
            payment_transaction_hash=PAYMENT_HASH,
            consumption_transaction_hash=CONSUME_HASH,
        )

    def test_confirms_exact_usdc_transfer_after_registry_consumption(self):
        result = self.confirm()
        self.assertTrue(result["verified"])
        self.assertEqual(result["chain_id"], ARC_CHAIN_ID)
        self.assertEqual(result["sender"], SENDER)
        self.assertEqual(result["recipient"], RECIPIENT)
        self.assertEqual(result["amount_base_units"], str(AMOUNT))
        self.assertEqual(result["payment_block_number"], 100)
        self.assertEqual(result["consumption_block_number"], 100)
        self.assertEqual(result["payment_transaction_index"], 2)
        self.assertEqual(result["finalized_block_number"], 101)

    def test_rejects_wrong_payment_sender(self):
        self.rpc.payment_tx["from"] = RECIPIENT
        with self.assertRaisesRegex(ArcPaymentVerificationError, "sender does not match"):
            self.confirm()

    def test_rejects_payment_without_matching_transfer_event(self):
        self.rpc.payment_receipt["logs"][0]["data"] = "0x" + word(AMOUNT + 1)
        with self.assertRaisesRegex(ArcPaymentVerificationError, "Transfer event"):
            self.confirm()

    def test_rejects_payment_before_registry_consumption(self):
        self.rpc.payment_receipt["transactionIndex"] = "0x0"
        with self.assertRaisesRegex(ArcPaymentVerificationError, "not ordered after"):
            self.confirm()

    def test_rejects_unfinalized_payment_block(self):
        self.rpc.finalized = {"number": "0x63", "hash": FINALIZED_BLOCK_HASH}
        with self.assertRaisesRegex(ArcPaymentVerificationError, "not finalized"):
            self.confirm()

    def test_rejects_failed_registry_consumption_receipt(self):
        self.rpc.consumption_receipt["status"] = "0x0"
        with self.assertRaisesRegex(ArcPaymentVerificationError, "consumption transaction did not succeed"):
            self.confirm()


if __name__ == "__main__":
    unittest.main()
