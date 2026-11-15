// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { IReactive } from "@reactive/src/interfaces/IReactive.sol";
import { ISystemContract } from "@reactive/src/interfaces/ISystemContract.sol";
import { VerigateReactiveGuard } from "../src/VerigateReactiveGuard.sol";

interface VmReactive {
    struct Log {
        bytes32[] topics;
        bytes data;
        address emitter;
    }

    function prank(address sender) external;
    function warp(uint256 timestamp) external;
    function etch(address target, bytes calldata code) external;
    function store(address target, bytes32 slot, bytes32 value) external;
    function load(address target, bytes32 slot) external view returns (bytes32);
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
}

contract ReactiveSystemStub {
    uint256 public callbackRequests;

    fallback() external payable {
        if (msg.sig == ISystemContract.requestCallbackV_1_0.selector) {
            callbackRequests += 1;
        }
    }
}

contract VerigateReactiveGuardTest {
    VmReactive private constant vm = VmReactive(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 private constant SYSTEM = uint160(0x8888888888888888888888888888888888888888);
    uint256 private constant ORIGIN_CHAIN_ID = 84532;
    uint256 private constant DESTINATION_CHAIN_ID = 1301;
    address private constant ORIGIN_HUB = address(0xBEEF);
    address private constant DESTINATION_RECEIVER = address(0xCAFE);
    address private constant AUTHORIZATION_ISSUER = address(0x1A55);

    VerigateReactiveGuard private guard;

    function setUp() public {
        ReactiveSystemStub stub = new ReactiveSystemStub();
        address systemAddress = address(uint160(SYSTEM));
        vm.etch(systemAddress, address(stub).code);
        vm.store(systemAddress, bytes32(0), bytes32(0));
        guard = new VerigateReactiveGuard(
            ORIGIN_CHAIN_ID,
            ORIGIN_HUB,
            DESTINATION_CHAIN_ID,
            200_000
        );
        guard.setDestinationReceiver(DESTINATION_RECEIVER);
    }

    function _authorizationLog(
        bytes32 id,
        address recipient,
        uint256 amountWei,
        uint64 expiry
    ) internal view returns (IReactive.LogRecord memory log_) {
        bytes32 actionDigest = keccak256("verigate-action");
        bytes32 policyHash = keccak256("verigate-policy");
        bytes32 receiptHash = keccak256("decision-receipt");
        bytes32 actionHash = keccak256(
            abi.encode(
                ORIGIN_CHAIN_ID,
                ORIGIN_HUB,
                AUTHORIZATION_ISSUER,
                id,
                actionDigest,
                policyHash,
                receiptHash,
                DESTINATION_CHAIN_ID,
                DESTINATION_RECEIVER,
                recipient,
                amountWei,
                expiry
            )
        );

        log_ = IReactive.LogRecord({
            chainId: ORIGIN_CHAIN_ID,
            contractAddress: ORIGIN_HUB,
            topic0: uint256(keccak256("AuthorizationRegistered(bytes32,bytes32,address,bytes32,bytes32,bytes32,uint256,uint64,uint256,address,address)")),
            topic1: uint256(id),
            topic2: uint256(actionHash),
            topic3: uint256(uint160(recipient)),
            data: abi.encode(
                actionDigest,
                policyHash,
                receiptHash,
                amountWei,
                expiry,
                DESTINATION_CHAIN_ID,
                DESTINATION_RECEIVER,
                AUTHORIZATION_ISSUER
            ),
            blockNumber: 1,
            opCode: 4,
            blockHash: 1,
            txHash: 1,
            logIndex: 0
        });
    }

    function _requestLog(
        bytes32 id,
        address recipient,
        uint256 amountWei,
        address requestedBy
    ) internal pure returns (IReactive.LogRecord memory log_) {
        log_ = IReactive.LogRecord({
            chainId: ORIGIN_CHAIN_ID,
            contractAddress: ORIGIN_HUB,
            topic0: uint256(keccak256("ExecutionRequested(bytes32,address,address,uint256,uint256,address)")),
            topic1: uint256(id),
            topic2: uint256(uint160(recipient)),
            topic3: uint256(uint160(requestedBy)),
            data: abi.encode(amountWei, DESTINATION_CHAIN_ID, DESTINATION_RECEIVER),
            blockNumber: 2,
            opCode: 4,
            blockHash: 2,
            txHash: 2,
            logIndex: 0
        });
    }

    function _react(IReactive.LogRecord memory log_) internal {
        vm.prank(address(uint160(SYSTEM)));
        guard.react(log_);
    }

    function _assertActionBlocked(uint8 expectedReason) internal {
        VmReactive.Log[] memory logs = vm.getRecordedLogs();
        bytes32 blockedTopic = keccak256("ActionBlocked(bytes32,address,uint256,uint8)");

        for (uint256 i = 0; i < logs.length; i++) {
            if (
                logs[i].emitter == address(guard) &&
                logs[i].topics.length > 0 &&
                logs[i].topics[0] == blockedTopic
            ) {
                (, uint8 reason) = abi.decode(logs[i].data, (uint256, uint8));
                require(reason == expectedReason, "unexpected block reason");
                return;
            }
        }

        revert("ActionBlocked evidence missing");
    }

    function testChangedAmountIsBlockedBeforeCallback() external {
        bytes32 id = keccak256("auth-changed-amount");
        address recipient = address(0xBEEF);
        _react(_authorizationLog(id, recipient, 1 ether, uint64(block.timestamp + 120)));
        vm.recordLogs();
        _react(_requestLog(id, recipient, 2 ether, AUTHORIZATION_ISSUER));

        VerigateReactiveGuard.CachedAuthorization memory cached = guard.getAuthorization(id);
        require(cached.exists, "authorization not cached");
        require(!cached.consumed, "mismatched request consumed authorization");
        require(
            uint256(vm.load(address(uint160(SYSTEM)), bytes32(0))) == 0,
            "blocked action requested destination callback"
        );

        VmReactive.Log[] memory logs = vm.getRecordedLogs();
        bytes32 blockedTopic = keccak256("ActionBlocked(bytes32,address,uint256,uint8)");
        bool blockedEvidenceFound;
        for (uint256 i = 0; i < logs.length; i++) {
            if (
                logs[i].emitter == address(guard) &&
                logs[i].topics.length > 0 &&
                logs[i].topics[0] == blockedTopic
            ) {
                blockedEvidenceFound = true;
                break;
            }
        }
        require(blockedEvidenceFound, "ActionBlocked evidence missing");
    }

    function testExactRequestIsAllowedAndOneTimeOnly() external {
        bytes32 id = keccak256("auth-valid");
        address recipient = address(0xBEEF);
        uint256 amountWei = 1 ether;
        _react(_authorizationLog(id, recipient, amountWei, uint64(block.timestamp + 120)));
        _react(_requestLog(id, recipient, amountWei, AUTHORIZATION_ISSUER));

        VerigateReactiveGuard.CachedAuthorization memory cached = guard.getAuthorization(id);
        require(cached.consumed, "valid request did not consume authorization");
        require(
            uint256(vm.load(address(uint160(SYSTEM)), bytes32(0))) == 1,
            "valid action did not request exactly one callback"
        );

        // A second matching request is treated as a replay; it cannot reopen
        // the authorization or produce a second callback request.
        vm.recordLogs();
        _react(_requestLog(id, recipient, amountWei, AUTHORIZATION_ISSUER));
        cached = guard.getAuthorization(id);
        require(cached.consumed, "replay changed consumed state");
        require(
            uint256(vm.load(address(uint160(SYSTEM)), bytes32(0))) == 1,
            "replay requested another callback"
        );
    }


    function testUnauthorizedRequesterIsBlockedBeforeCallback() external {
        bytes32 id = keccak256("auth-wrong-requester");
        address recipient = address(0xBEEF);
        _react(_authorizationLog(id, recipient, 1 ether, uint64(block.timestamp + 120)));
        _react(_requestLog(id, recipient, 1 ether, address(0xBAD)));

        VerigateReactiveGuard.CachedAuthorization memory cached = guard.getAuthorization(id);
        require(!cached.consumed, "unauthorized requester consumed authorization");
        require(
            uint256(vm.load(address(uint160(SYSTEM)), bytes32(0))) == 0,
            "unauthorized requester triggered a callback"
        );
    }

    function testMalformedRecipientTopicRejectsRegistration() external {
        bytes32 id = keccak256("auth-malformed-registration");
        address recipient = address(0xBEEF);

        IReactive.LogRecord memory log_ =
            _authorizationLog(id, recipient, 1 ether, uint64(block.timestamp + 120));

        log_.topic3 = (uint256(1) << 160) | uint256(uint160(recipient));

        _react(log_);

        VerigateReactiveGuard.CachedAuthorization memory cached = guard.getAuthorization(id);
        require(!cached.exists, "malformed recipient topic was accepted");
    }

    function testMalformedRecipientTopicBlocksExecution() external {
        bytes32 id = keccak256("auth-malformed-recipient");
        address recipient = address(0xBEEF);

        _react(_authorizationLog(id, recipient, 1 ether, uint64(block.timestamp + 120)));

        IReactive.LogRecord memory log_ =
            _requestLog(id, recipient, 1 ether, AUTHORIZATION_ISSUER);
        log_.topic2 = (uint256(1) << 160) | uint256(uint160(recipient));

        vm.recordLogs();
        _react(log_);

        VerigateReactiveGuard.CachedAuthorization memory cached = guard.getAuthorization(id);
        require(!cached.consumed, "malformed recipient topic consumed authorization");
        require(
            uint256(vm.load(address(uint160(SYSTEM)), bytes32(0))) == 0,
            "malformed recipient topic triggered callback"
        );
        _assertActionBlocked(guard.BLOCK_MALFORMED_ADDRESS_TOPIC());
    }

    function testMalformedRequesterTopicCannotImpersonateIssuer() external {
        bytes32 id = keccak256("auth-malformed-requester");
        address recipient = address(0xBEEF);

        _react(_authorizationLog(id, recipient, 1 ether, uint64(block.timestamp + 120)));

        IReactive.LogRecord memory log_ =
            _requestLog(id, recipient, 1 ether, AUTHORIZATION_ISSUER);

        // uint160 truncation would otherwise turn this into AUTHORIZATION_ISSUER.
        log_.topic3 =
            (uint256(1) << 160) | uint256(uint160(AUTHORIZATION_ISSUER));

        vm.recordLogs();
        _react(log_);

        VerigateReactiveGuard.CachedAuthorization memory cached = guard.getAuthorization(id);
        require(!cached.consumed, "malformed requester topic consumed authorization");
        require(
            uint256(vm.load(address(uint160(SYSTEM)), bytes32(0))) == 0,
            "malformed requester topic triggered callback"
        );
        _assertActionBlocked(guard.BLOCK_MALFORMED_ADDRESS_TOPIC());
    }

    function testExpiredAuthorizationIsNotConsumed() external {
        bytes32 id = keccak256("auth-expired");
        address recipient = address(0xBEEF);
        uint64 expiry = uint64(block.timestamp + 30);
        _react(_authorizationLog(id, recipient, 1 ether, expiry));
        vm.warp(uint256(expiry) + 1);
        _react(_requestLog(id, recipient, 1 ether, AUTHORIZATION_ISSUER));

        VerigateReactiveGuard.CachedAuthorization memory cached = guard.getAuthorization(id);
        require(!cached.consumed, "expired request consumed authorization");
        require(
            uint256(vm.load(address(uint160(SYSTEM)), bytes32(0))) == 0,
            "expired request requested destination callback"
        );
    }
}
