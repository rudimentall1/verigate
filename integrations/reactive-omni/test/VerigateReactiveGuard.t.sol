// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { IReactive } from "@reactive/src/interfaces/IReactive.sol";
import { VerigateReactiveGuard } from "../src/VerigateReactiveGuard.sol";

interface VmReactive {
    function prank(address sender) external;
    function warp(uint256 timestamp) external;
    function etch(address target, bytes calldata code) external;
}

contract ReactiveSystemStub {
    fallback() external payable {}
}

contract VerigateReactiveGuardTest {
    VmReactive private constant vm = VmReactive(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 private constant SYSTEM = uint160(0x8888888888888888888888888888888888888888);
    uint256 private constant ORIGIN_CHAIN_ID = 84532;
    uint256 private constant DESTINATION_CHAIN_ID = 1301;
    address private constant ORIGIN_HUB = address(0xBEEF);
    address private constant DESTINATION_RECEIVER = address(0xCAFE);

    VerigateReactiveGuard private guard;

    function setUp() public {
        ReactiveSystemStub stub = new ReactiveSystemStub();
        vm.etch(address(uint160(SYSTEM)), address(stub).code);
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
            topic0: uint256(keccak256("AuthorizationRegistered(bytes32,bytes32,address,bytes32,bytes32,bytes32,uint256,uint64,uint256,address)")),
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
                DESTINATION_RECEIVER
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
        uint256 amountWei
    ) internal pure returns (IReactive.LogRecord memory log_) {
        log_ = IReactive.LogRecord({
            chainId: ORIGIN_CHAIN_ID,
            contractAddress: ORIGIN_HUB,
            topic0: uint256(keccak256("ExecutionRequested(bytes32,address,uint256,uint256,address)")),
            topic1: uint256(id),
            topic2: uint256(uint160(recipient)),
            topic3: 0,
            data: abi.encode(amountWei, DESTINATION_CHAIN_ID, DESTINATION_RECEIVER),
            blockNumber: 2,
            opCode: 3,
            blockHash: 2,
            txHash: 2,
            logIndex: 0
        });
    }

    function _react(IReactive.LogRecord memory log_) internal {
        vm.prank(address(uint160(SYSTEM)));
        guard.react(log_);
    }

    function testChangedAmountIsBlockedBeforeCallback() external {
        bytes32 id = keccak256("auth-changed-amount");
        address recipient = address(0xBEEF);
        _react(_authorizationLog(id, recipient, 1 ether, uint64(block.timestamp + 120)));
        _react(_requestLog(id, recipient, 2 ether));

        VerigateReactiveGuard.CachedAuthorization memory cached = guard.getAuthorization(id);
        require(cached.exists, "authorization not cached");
        require(!cached.consumed, "mismatched request consumed authorization");
    }

    function testExactRequestIsAllowedAndOneTimeOnly() external {
        bytes32 id = keccak256("auth-valid");
        address recipient = address(0xBEEF);
        uint256 amountWei = 1 ether;
        _react(_authorizationLog(id, recipient, amountWei, uint64(block.timestamp + 120)));
        _react(_requestLog(id, recipient, amountWei));

        VerigateReactiveGuard.CachedAuthorization memory cached = guard.getAuthorization(id);
        require(cached.consumed, "valid request did not consume authorization");

        // A second matching request is treated as a replay; it cannot reopen
        // the authorization or produce a second callback request.
        _react(_requestLog(id, recipient, amountWei));
        cached = guard.getAuthorization(id);
        require(cached.consumed, "replay changed consumed state");
    }

    function testExpiredAuthorizationIsNotConsumed() external {
        bytes32 id = keccak256("auth-expired");
        address recipient = address(0xBEEF);
        uint64 expiry = uint64(block.timestamp + 30);
        _react(_authorizationLog(id, recipient, 1 ether, expiry));
        vm.warp(uint256(expiry) + 1);
        _react(_requestLog(id, recipient, 1 ether));

        VerigateReactiveGuard.CachedAuthorization memory cached = guard.getAuthorization(id);
        require(!cached.consumed, "expired request consumed authorization");
    }
}
