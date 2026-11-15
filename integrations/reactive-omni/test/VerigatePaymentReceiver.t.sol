// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { IPayable } from "@reactive/src/interfaces/IPayable.sol";
import { VerigatePaymentReceiver } from "../src/VerigatePaymentReceiver.sol";

interface VmReceiver {
    function prank(address sender) external;
    function deal(address account, uint256 newBalance) external;
    function expectRevert() external;
}

contract VerigatePaymentReceiverTest {
    VmReceiver private constant vm = VmReceiver(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant CALLBACK_PROXY = address(0xCA11);
    address private constant REACTIVE_SENDER = address(0xA11CE);
    address private constant AUTHORIZATION_ISSUER = address(0x1A55);
    uint256 private constant ORIGIN_CHAIN_ID = 84532;
    address private constant ORIGIN_HUB = address(0xBEEF);

    function _deploy() internal returns (VerigatePaymentReceiver) {
        return new VerigatePaymentReceiver(
            IPayable(payable(CALLBACK_PROXY)),
            REACTIVE_SENDER,
            ORIGIN_CHAIN_ID,
            ORIGIN_HUB
        );
    }

    function _actionHash(
        VerigatePaymentReceiver receiver,
        bytes32 authorizationId,
        address issuer,
        address payable recipient,
        uint256 amountWei,
        uint64 expiresAt,
        bytes32 actionDigest,
        bytes32 policyHash,
        bytes32 receiptHash
    ) internal view returns (bytes32) {
        return keccak256(
            abi.encode(
                ORIGIN_CHAIN_ID,
                ORIGIN_HUB,
                issuer,
                authorizationId,
                actionDigest,
                policyHash,
                receiptHash,
                block.chainid,
                address(receiver),
                recipient,
                amountWei,
                expiresAt
            )
        );
    }

    function testAuthenticCallbackExecutesOnePayment() external {
        VerigatePaymentReceiver receiver = _deploy();
        bytes32 id = keccak256("payment-1");
        bytes32 actionDigest = keccak256("action");
        bytes32 policyHash = keccak256("policy");
        bytes32 receiptHash = keccak256("receipt");
        address payable recipient = payable(address(0xB0B));
        uint256 amountWei = 0.1 ether;
        uint64 expiry = uint64(block.timestamp + 120);
        bytes32 commitment = _actionHash(
            receiver, id, AUTHORIZATION_ISSUER, recipient, amountWei, expiry, actionDigest, policyHash, receiptHash
        );

        vm.deal(address(receiver), amountWei);
        uint256 balanceBefore = recipient.balance;

        vm.prank(CALLBACK_PROXY);
        receiver.executeAuthorizedPayment(
            REACTIVE_SENDER,
            id,
            AUTHORIZATION_ISSUER,
            recipient,
            amountWei,
            expiry,
            commitment,
            actionDigest,
            policyHash,
            receiptHash
        );

        require(recipient.balance == balanceBefore + amountWei, "payment was not transferred");
        require(receiver.consumed(id), "authorization not consumed");
    }

    function testRejectsForgedCallbackProxy() external {
        VerigatePaymentReceiver receiver = _deploy();
        vm.expectRevert();
        vm.prank(address(0xBAD));
        receiver.executeAuthorizedPayment(
            REACTIVE_SENDER,
            keccak256("forged"),
            AUTHORIZATION_ISSUER,
            payable(address(0xB0B)),
            1,
            uint64(block.timestamp + 60),
            bytes32(0),
            bytes32(uint256(1)),
            bytes32(uint256(2)),
            bytes32(uint256(3))
        );
    }

    function testRejectsWrongReactiveSenderBehindValidProxy() external {
        VerigatePaymentReceiver receiver = _deploy();
        vm.expectRevert();
        vm.prank(CALLBACK_PROXY);
        receiver.executeAuthorizedPayment(
            address(0xBAD),
            keccak256("wrong-reactive-sender"),
            AUTHORIZATION_ISSUER,
            payable(address(0xB0B)),
            1,
            uint64(block.timestamp + 60),
            bytes32(0),
            bytes32(uint256(1)),
            bytes32(uint256(2)),
            bytes32(uint256(3))
        );
    }

    function testRejectsModifiedActionCommitment() external {
        VerigatePaymentReceiver receiver = _deploy();
        bytes32 id = keccak256("payment-2");
        vm.expectRevert();
        vm.prank(CALLBACK_PROXY);
        receiver.executeAuthorizedPayment(
            REACTIVE_SENDER,
            id,
            payable(address(0xB0B)),
            1,
            uint64(block.timestamp + 60),
            bytes32(uint256(99)),
            bytes32(uint256(1)),
            bytes32(uint256(2)),
            bytes32(uint256(3))
        );
    }
}
