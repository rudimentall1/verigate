import unittest

from Crypto.Hash import keccak

from integrations.arc_authority_registry import (
    ARC_CHAIN_ID,
    DEFAULT_EXECUTOR,
    DEFAULT_REGISTRY,
    REGISTER_SELECTOR,
    CONSUME_SELECTOR,
    ISSUER_SELECTOR,
    ArcAuthorityRegistry,
)

AGENT_EXECUTOR = "0x3333333333333333333333333333333333333333"


def _test_runtime_hash():
    hasher = keccak.new(digest_bits=256)
    hasher.update(bytes.fromhex("60006000"))
    return "0x" + hasher.hexdigest()


class FakeRpc:
    endpoint = "https://rpc.mainnet.arc.io"

    def chain_id(self):
        return ARC_CHAIN_ID

    def get_code(self, address):
        return "0x60006000"

    issuer_enabled = True

    def eth_call(self, to, data):
        if data == "0x8da5cb5b":
            return "0x" + "0" * 24 + DEFAULT_EXECUTOR[2:].lower()
        if data.startswith(ISSUER_SELECTOR):
            return "0x" + format(int(self.issuer_enabled), "064x")
        raise AssertionError(f"Unexpected eth_call: {data}")


class ArcAuthorityRegistryEncodingTest(unittest.TestCase):
    def setUp(self):
        self.registry = ArcAuthorityRegistry(rpc=FakeRpc(), expected_code_hash=_test_runtime_hash())

    def authorization(self):
        return {
            "payload": {
                "authorization_id": "ab" * 32,
                "expires_at": 1999999999,
                "intent_id": "arc-test-intent",
                "action": {
                    "metadata": {
                        "evm_transaction": {"from": AGENT_EXECUTOR},
                    },
                },
            },
            "signature": "test-signature",
            "algorithm": "Ed25519",
        }

    def test_deployment_verification_checks_chain_code_and_owner(self):
        result = self.registry.verify_deployment()
        self.assertTrue(result["verified"])
        self.assertEqual(result["chain_id"], 5042)
        self.assertEqual(result["contract_address"].lower(), DEFAULT_REGISTRY.lower())
        self.assertEqual(result["owner"], DEFAULT_EXECUTOR.lower())

    def test_deployment_verification_rejects_disabled_executor_issuer(self):
        rpc = FakeRpc()
        rpc.issuer_enabled = False
        registry = ArcAuthorityRegistry(rpc=rpc, expected_code_hash=_test_runtime_hash())
        with self.assertRaisesRegex(Exception, "not an enabled Registry issuer"):
            registry.verify_deployment()

    def test_deployment_verification_rejects_missing_runtime_hash_pin(self):
        registry = ArcAuthorityRegistry(rpc=FakeRpc(), expected_code_hash="")
        with self.assertRaisesRegex(Exception, "VERIGATE_ARC_REGISTRY_CODE_HASH"):
            registry.verify_deployment()

    def test_deployment_verification_rejects_runtime_hash_mismatch(self):
        registry = ArcAuthorityRegistry(
            rpc=FakeRpc(),
            expected_code_hash="0x" + "00" * 32,
        )
        with self.assertRaisesRegex(Exception, "bytecode hash mismatch"):
            registry.verify_deployment()

    def test_registration_transaction_binds_authorization_and_executor(self):
        result = self.registry.prepare_registration_transaction(self.authorization())
        tx = result["registration_transaction"]
        self.assertEqual(tx["chainId"], hex(ARC_CHAIN_ID))
        self.assertEqual(tx["from"], DEFAULT_EXECUTOR.lower())
        self.assertEqual(result["issuer"], DEFAULT_EXECUTOR.lower())
        self.assertEqual(result["executor"], AGENT_EXECUTOR.lower())
        self.assertEqual(tx["to"], DEFAULT_REGISTRY.lower())
        self.assertIn(AGENT_EXECUTOR.lower()[2:].rjust(64, "0"), tx["data"])
        self.assertTrue(tx["data"].startswith(REGISTER_SELECTOR))
        self.assertEqual(result["authorization_id"], "0x" + "ab" * 32)
        self.assertEqual(len(result["intent_hash"]), 66)

    def test_intent_hash_is_bound_to_configured_registry_address(self):
        authorization = self.authorization()
        default_hash = self.registry._authorization_values(authorization)[1]

        alternate_registry = ArcAuthorityRegistry(
            rpc=FakeRpc(),
            contract_address="0x1111111111111111111111111111111111111111",
        )
        alternate_hash = alternate_registry._authorization_values(authorization)[1]

        self.assertNotEqual(default_hash, alternate_hash)

    def test_consume_calldata_selector_is_expected_contract_method(self):
        self.assertEqual(CONSUME_SELECTOR, "0xbad56b75")


if __name__ == "__main__":
    unittest.main()


def test_confirmed_receipt_checks_actual_transaction_fields():
    import pytest
    from integrations.arc_authority_registry import (
        ArcAuthorityRegistry,
        ArcAuthorityRegistryError,
    )

    tx_hash = "0x" + "ab" * 32
    registry_address = "0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D"
    executor_address = "0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C"
    calldata = "0x12345678"

    class FakeRpc:
        def __init__(self, transaction):
            self.transaction = transaction

        def get_transaction_receipt(self, _):
            return {
                "transactionHash": tx_hash,
                "status": "0x1",
                "to": registry_address,
                "from": executor_address,
                "blockNumber": "0x100",
            }

        def get_transaction_by_hash(self, _):
            return self.transaction

    def make_registry(transaction):
        registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
        registry.rpc = FakeRpc(transaction)
        registry.contract_address = registry_address.lower()
        registry.executor_address = executor_address.lower()
        return registry

    valid_transaction = {
        "hash": tx_hash,
        "chainId": "0x13b2",
        "to": registry_address,
        "from": executor_address,
        "input": calldata,
        "value": "0x0",
    }

    # Correct transaction must pass.
    assert make_registry(valid_transaction)._confirmed_receipt(
        tx_hash, calldata
    )["status"] == "0x1"

    invalid_transactions = [
        ("wrong chain", {**valid_transaction, "chainId": "0x1"}),
        ("wrong contract", {**valid_transaction, "to": executor_address}),
        ("wrong sender", {**valid_transaction, "from": registry_address}),
        ("wrong calldata", {**valid_transaction, "input": "0xdeadbeef"}),
        ("nonzero value", {**valid_transaction, "value": "0x1"}),
        ("wrong transaction hash", {**valid_transaction, "hash": "0x" + "cd" * 32}),
    ]

    for label, transaction in invalid_transactions:
        with pytest.raises(ArcAuthorityRegistryError):
            make_registry(transaction)._confirmed_receipt(tx_hash, calldata)

    # Missing transaction details must fail closed.
    with pytest.raises(ArcAuthorityRegistryError):
        make_registry(None)._confirmed_receipt(tx_hash, calldata)


def test_confirmed_receipt_rejects_mismatched_receipt_hash():
    import pytest
    from integrations.arc_authority_registry import (
        ArcAuthorityRegistry,
        ArcAuthorityRegistryError,
    )

    tx_hash = "0x" + "ab" * 32
    registry_address = "0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D"
    executor_address = "0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C"
    calldata = "0x12345678"

    class FakeRpc:
        def get_transaction_receipt(self, _):
            return {
                "transactionHash": None,
                "status": "0x1",
                "to": registry_address,
                "from": executor_address,
                "blockNumber": "0x100",
            }

        def get_transaction_by_hash(self, _):
            return {
                "hash": tx_hash,
                "chainId": "0x13b2",
                "to": registry_address,
                "from": executor_address,
                "input": calldata,
                "value": "0x0",
            }

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.rpc = FakeRpc()
    registry.contract_address = registry_address.lower()
    registry.executor_address = executor_address.lower()

    with pytest.raises(ArcAuthorityRegistryError):
        registry._confirmed_receipt(tx_hash, calldata)


def test_expired_authorization_can_be_parsed_only_for_confirmation():
    import pytest
    from integrations.arc_authority_registry import ArcAuthorityRegistryError

    registry = ArcAuthorityRegistry(rpc=FakeRpc())
    authorization = {
        "payload": {
            "authorization_id": "ab" * 32,
            "expires_at": 1,
            "intent_id": "expired-test",
        },
        "signature": "test-signature",
        "algorithm": "Ed25519",
    }

    with pytest.raises(ArcAuthorityRegistryError, match="expired"):
        registry._authorization_values(authorization)

    authorization_id, intent_hash, valid_until = registry._authorization_values(
        authorization, require_unexpired=False
    )
    assert authorization_id == "ab" * 32
    assert len(intent_hash) == 64
    assert valid_until == 1


def test_inclusion_block_expiry_check_accepts_pre_expiry_block():
    from integrations.arc_authority_registry import ArcAuthorityRegistry

    class BlockRpc:
        def get_block_by_tag(self, tag):
            assert tag == "finalized"
            block = self.get_block_by_number(256)
            if block is not None and isinstance(block.get("number"), int):
                block = {**block, "number": hex(block["number"])}
            return block

        def get_block_by_number(self, number):
            assert number == 256
            return {
                "number": "0x100",
                "timestamp": "0x64",
                "hash": "0x1111111111111111111111111111111111111111111111111111111111111111",
            }

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.rpc = BlockRpc()

    registry._verify_inclusion_before_expiry(
        {"blockNumber": "0x100", "blockHash": "0x1111111111111111111111111111111111111111111111111111111111111111"},
        101,
    )


def test_inclusion_block_expiry_check_rejects_post_expiry_block():
    import pytest
    from integrations.arc_authority_registry import (
        ArcAuthorityRegistry,
        ArcAuthorityRegistryError,
    )

    class BlockRpc:
        def get_block_by_tag(self, tag):
            assert tag == "finalized"
            block = self.get_block_by_number(256)
            if block is not None and isinstance(block.get("number"), int):
                block = {**block, "number": hex(block["number"])}
            return block

        def get_block_by_number(self, number):
            return {
                "number": number,
                "timestamp": "0x65",
                "hash": "0x1111111111111111111111111111111111111111111111111111111111111111",
            }

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.rpc = BlockRpc()

    with pytest.raises(ArcAuthorityRegistryError, match="after authorization expiry"):
        registry._verify_inclusion_before_expiry(
            {"blockNumber": "0x100", "blockHash": "0x1111111111111111111111111111111111111111111111111111111111111111"},
            100,
        )


def test_inclusion_block_expiry_check_fails_closed_without_block():
    import pytest
    from integrations.arc_authority_registry import (
        ArcAuthorityRegistry,
        ArcAuthorityRegistryError,
    )

    class BlockRpc:
        def get_block_by_tag(self, tag):
            assert tag == "finalized"
            block = self.get_block_by_number(256)
            if block is not None and isinstance(block.get("number"), int):
                block = {**block, "number": hex(block["number"])}
            return block

        def get_block_by_number(self, number):
            return None

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.rpc = BlockRpc()

    with pytest.raises(ArcAuthorityRegistryError, match="unavailable"):
        registry._verify_inclusion_before_expiry(
            {"blockNumber": "0x100"},
            100,
        )


def test_inclusion_block_rejects_timestamp_equal_to_expiry():
    import pytest
    from integrations.arc_authority_registry import (
        ArcAuthorityRegistry,
        ArcAuthorityRegistryError,
    )

    class BlockRpc:
        def get_block_by_tag(self, tag):
            assert tag == "finalized"
            block = self.get_block_by_number(256)
            if block is not None and isinstance(block.get("number"), int):
                block = {**block, "number": hex(block["number"])}
            return block

        def get_block_by_number(self, number):
            return {
                "number": number,
                "timestamp": "0x64",
                "hash": "0x1111111111111111111111111111111111111111111111111111111111111111",
            }

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.rpc = BlockRpc()

    with pytest.raises(ArcAuthorityRegistryError, match="at or after"):
        registry._verify_inclusion_before_expiry(
            {
                "blockNumber": "0x100",
                "blockHash": "0x1111111111111111111111111111111111111111111111111111111111111111",
            },
            100,
            valid_from=50,
        )


def test_inclusion_block_rejects_timestamp_before_issuance():
    import pytest
    from integrations.arc_authority_registry import ArcAuthorityRegistryError

    class BlockRpc:
        def get_block_by_tag(self, tag):
            assert tag == "finalized"
            block = self.get_block_by_number(256)
            if block is not None and isinstance(block.get("number"), int):
                block = {**block, "number": hex(block["number"])}
            return block

        def get_block_by_number(self, number):
            return {
                "number": number,
                "timestamp": "0x64",
                "hash": "0x1111111111111111111111111111111111111111111111111111111111111111",
            }

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.rpc = BlockRpc()

    with pytest.raises(ArcAuthorityRegistryError, match="before authorization issuance"):
        registry._verify_inclusion_before_expiry(
            {
                "blockNumber": "0x100",
                "blockHash": "0x1111111111111111111111111111111111111111111111111111111111111111",
            },
            200,
            valid_from=101,
        )



class ArcAuthorityRegistryFlowTest(unittest.TestCase):
    def test_full_registration_and_consumption_confirmation_verify_registry_state(self):
        from integrations.arc_authority_registry import (
            CONSUMED_EVENT,
            GET_AUTHORIZATION_SELECTOR,
            REGISTERED_EVENT,
            ArcAuthorityRegistry,
        )
    
        registry_address = DEFAULT_REGISTRY.lower()
        issuer = DEFAULT_EXECUTOR.lower()
        executor = AGENT_EXECUTOR.lower()
        authorization = {
            "payload": {
                "authorization_id": "ab" * 32,
                "issued_at": 90,
                "expires_at": 2000,
                "intent_id": "arc-registry-flow",
                "action": {"metadata": {"evm_transaction": {"from": executor}}},
            },
            "signature": "test-signature",
            "algorithm": "Ed25519",
        }
    
        registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
        registry.contract_address = registry_address
        registry.executor_address = issuer
        registry.issuer_address = issuer
        registry.expected_code_hash = _test_runtime_hash()
        authorization_id, intent_hash, valid_until = registry._authorization_values(
            authorization, require_unexpired=False
        )
    
        registration_hash = "0x" + "11" * 32
        consumption_hash = "0x" + "22" * 32
        registration_block_hash = "0x" + "33" * 32
        consumption_block_hash = "0x" + "44" * 32
    
        def word(value):
            return format(value, "064x")
    
        def topic_address(address):
            return "0x" + address[2:].rjust(64, "0")
    
        registration_log = {
            "address": registry_address,
            "topics": [
                REGISTERED_EVENT,
                "0x" + authorization_id,
                "0x" + intent_hash,
                topic_address(executor),
            ],
            "data": "0x" + word(valid_until) + word(int(issuer, 16)),
        }
        consumption_log = {
            "address": registry_address,
            "topics": [
                CONSUMED_EVENT,
                "0x" + authorization_id,
                "0x" + intent_hash,
                topic_address(executor),
            ],
            "data": "0x",
        }
    
        def make_transaction(tx_hash, calldata, sender):
            return {
                "hash": tx_hash,
                "chainId": hex(ARC_CHAIN_ID),
                "to": registry_address,
                "from": sender,
                "input": calldata,
                "value": "0x0",
            }
    
        registration_calldata = (
            REGISTER_SELECTOR
            + authorization_id
            + intent_hash
            + word(int(executor, 16))
            + word(valid_until)
        )
        consumption_calldata = CONSUME_SELECTOR + authorization_id + intent_hash
    
        class FlowRpc:
            consumed = False
    
            def chain_id(self):
                return ARC_CHAIN_ID
    
            def get_code(self, _):
                return "0x60006000"
    
            def eth_call(self, _, data):
                if data == "0x8da5cb5b":
                    return "0x" + "0" * 24 + issuer[2:]
                if data.startswith(ISSUER_SELECTOR):
                    return "0x" + format(1, "064x")
                if data == GET_AUTHORIZATION_SELECTOR + authorization_id:
                    return "0x" + "".join(
                        [
                            intent_hash,
                            word(int(executor, 16)),
                            word(valid_until),
                            word(100),
                            word(int(self.consumed)),
                            word(0),
                        ]
                    )
                raise AssertionError(f"Unexpected eth_call: {data}")
    
            def get_transaction_receipt(self, tx_hash):
                if tx_hash == registration_hash:
                    return {
                        "transactionHash": registration_hash,
                        "status": "0x1",
                        "to": registry_address,
                        "from": issuer,
                        "blockNumber": "0x64",
                        "blockHash": registration_block_hash,
                        "logs": [registration_log],
                    }
                if tx_hash == consumption_hash:
                    return {
                        "transactionHash": consumption_hash,
                        "status": "0x1",
                        "to": registry_address,
                        "from": executor,
                        "blockNumber": "0x65",
                        "blockHash": consumption_block_hash,
                        "logs": [consumption_log],
                    }
                return None
    
            def get_transaction_by_hash(self, tx_hash):
                if tx_hash == registration_hash:
                    return make_transaction(registration_hash, registration_calldata, issuer)
                if tx_hash == consumption_hash:
                    return make_transaction(consumption_hash, consumption_calldata, executor)
                return None
    
            def get_block_by_tag(self, tag):
                assert tag == "finalized"
                return {
                    "number": "0x65",
                    "timestamp": "0x65",
                    "hash": consumption_block_hash,
                }

            def get_block_by_number(self, number):
                if number == 100:
                    return {
                        "number": "0x64",
                        "timestamp": "0x64",
                        "hash": registration_block_hash,
                    }
                if number == 101:
                    return {
                        "number": "0x65",
                        "timestamp": "0x65",
                        "hash": consumption_block_hash,
                    }
                return None
    
        rpc = FlowRpc()
        registry.rpc = rpc
    
        registration = registry.confirm_registration(authorization, registration_hash)
        assert registration["registered"] is True
        assert registration["authorization_id"] == "0x" + authorization_id
        assert registration["consume_transaction"]["data"] == consumption_calldata
    
        rpc.consumed = True
        consumption = registry.confirm_consumption(authorization, consumption_hash)
        assert consumption["consumed"] is True
        assert consumption["transaction_ref"] == consumption_hash
        assert consumption["block_timestamp"] == 101
    


def test_find_event_rejects_topic0_with_matching_four_byte_prefix_only():
    import pytest
    from integrations.arc_authority_registry import (
        REGISTERED_EVENT,
        ArcAuthorityRegistry,
        ArcAuthorityRegistryError,
    )

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.contract_address = DEFAULT_REGISTRY.lower()
    registry.executor_address = DEFAULT_EXECUTOR.lower()
    authorization_id = "ab" * 32
    intent_hash = "cd" * 32
    address_topic = "0x" + DEFAULT_EXECUTOR.lower()[2:].rjust(64, "0")

    forged_log = {
        "address": DEFAULT_REGISTRY,
        "topics": [
            REGISTERED_EVENT[:10] + "0" * 56,
            "0x" + authorization_id,
            "0x" + intent_hash,
            address_topic,
        ],
    }

    with pytest.raises(ArcAuthorityRegistryError, match="event is missing"):
        registry._find_event(
            {"logs": [forged_log]},
            REGISTERED_EVENT,
            authorization_id,
            intent_hash,
            DEFAULT_EXECUTOR,
        )


def test_find_event_accepts_exact_full_topic0_hash():
    from integrations.arc_authority_registry import (
        REGISTERED_EVENT,
        ArcAuthorityRegistry,
    )

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.contract_address = DEFAULT_REGISTRY.lower()
    registry.executor_address = DEFAULT_EXECUTOR.lower()
    authorization_id = "ab" * 32
    intent_hash = "cd" * 32
    address_topic = "0x" + DEFAULT_EXECUTOR.lower()[2:].rjust(64, "0")

    exact_log = {
        "address": DEFAULT_REGISTRY,
        "topics": [
            REGISTERED_EVENT,
            "0x" + authorization_id,
            "0x" + intent_hash,
            address_topic,
        ],
    }

    assert registry._find_event(
        {"logs": [exact_log]},
        REGISTERED_EVENT,
        authorization_id,
        intent_hash,
        DEFAULT_EXECUTOR,
    ) == exact_log


def test_inclusion_block_must_be_at_or_below_arc_finalized_head():
    import pytest
    from integrations.arc_authority_registry import ArcAuthorityRegistry, ArcAuthorityRegistryError

    block_hash = "0x" + "11" * 32

    class Rpc:
        def get_block_by_number(self, number):
            return {"number": "0x100", "timestamp": "0x64", "hash": block_hash}

        def get_block_by_tag(self, tag):
            assert tag == "finalized"
            return {"number": "0xff", "hash": "0x" + "22" * 32}

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.rpc = Rpc()
    with pytest.raises(ArcAuthorityRegistryError, match="not yet finalized"):
        registry._verify_inclusion_before_expiry(
            {"blockNumber": "0x100", "blockHash": block_hash},
            101,
        )


def test_finalized_head_hash_must_match_inclusion_at_same_height():
    import pytest
    from integrations.arc_authority_registry import ArcAuthorityRegistry, ArcAuthorityRegistryError

    block_hash = "0x" + "11" * 32

    class Rpc:
        def get_block_by_number(self, number):
            return {"number": "0x100", "timestamp": "0x64", "hash": block_hash}

        def get_block_by_tag(self, tag):
            assert tag == "finalized"
            return {"number": "0x100", "hash": "0x" + "22" * 32}

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.rpc = Rpc()
    with pytest.raises(ArcAuthorityRegistryError, match="finalized block hash"):
        registry._verify_inclusion_before_expiry(
            {"blockNumber": "0x100", "blockHash": block_hash},
            101,
        )


def test_finalized_tag_unavailable_fails_closed():
    import pytest
    from integrations.arc_authority_registry import ArcAuthorityRegistry, ArcAuthorityRegistryError
    from enforcement.evm_rpc import EvmRpcError

    block_hash = "0x" + "11" * 32

    class Rpc:
        def get_block_by_number(self, number):
            return {"number": "0x100", "timestamp": "0x64", "hash": block_hash}

        def get_block_by_tag(self, tag):
            raise EvmRpcError("unsupported finalized tag")

    registry = ArcAuthorityRegistry.__new__(ArcAuthorityRegistry)
    registry.rpc = Rpc()
    with pytest.raises(ArcAuthorityRegistryError, match="finalized block lookup failed"):
        registry._verify_inclusion_before_expiry(
            {"blockNumber": "0x100", "blockHash": block_hash},
            101,
        )
