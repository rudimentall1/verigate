// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { IPayable } from "@reactive/src/interfaces/IPayable.sol";
import { AbstractCallback } from "@reactive/src/base/AbstractCallback.sol";

/// @title VerigatePaymentReceiver
/// @notice A pre-funded testnet execution vault. It pays only when the
///         configured Reactive contract delivers an authenticated callback
///         whose action commitment matches the origin-chain Verigate event.
///
/// @dev This is a demo executor, not a production non-custodial wallet. Funds
///      are held by this contract and must be supplied to it on the destination
///      chain before a payment can be executed.
contract VerigatePaymentReceiver is AbstractCallback {
    uint256 public immutable originChainId;
    address public immutable originHub;

    mapping(bytes32 => bool) public consumed;

    error InvalidConfiguration();
    error InvalidAuthorizationCommitment();
    error AuthorizationExpired();
    error AuthorizationAlreadyConsumed(bytes32 authorizationId);
    error InvalidPayment();
    error PaymentTransferFailed(address recipient, uint256 amountWei);

    event PaymentExecuted(
        bytes32 indexed authorizationId,
        address indexed recipient,
        address indexed issuer,
        uint256 amountWei,
        bytes32 actionHash,
        bytes32 verigateActionHash,
        bytes32 policySha256,
        bytes32 decisionReceiptSha256
    );

    constructor(
        IPayable callbackProxy_,
        address reactiveSender_,
        uint256 originChainId_,
        address originHub_
    )
        payable
        AbstractCallback(callbackProxy_, reactiveSender_)
    {
        if (
            address(callbackProxy_) == address(0) ||
            reactiveSender_ == address(0) ||
            originChainId_ == 0 ||
            originHub_ == address(0)
        ) revert InvalidConfiguration();

        originChainId = originChainId_;
        originHub = originHub_;
    }

    function executeAuthorizedPayment(
        address reactive_,
        bytes32 authorizationId,
        address issuer,
        address payable recipient,
        uint256 amountWei,
        uint64 expiresAt,
        bytes32 actionHash,
        bytes32 verigateActionHash,
        bytes32 policySha256,
        bytes32 decisionReceiptSha256
    ) external onlyServiceProvider onlyCallbackSender(reactive_) {
        if (block.timestamp >= expiresAt) revert AuthorizationExpired();
        if (authorizationId == bytes32(0) || recipient == address(0) || amountWei == 0) {
            revert InvalidPayment();
        }
        if (consumed[authorizationId]) {
            revert AuthorizationAlreadyConsumed(authorizationId);
        }

        bytes32 expectedActionHash = keccak256(
            abi.encode(
                originChainId,
                originHub,
                issuer,
                authorizationId,
                verigateActionHash,
                policySha256,
                decisionReceiptSha256,
                block.chainid,
                address(this),
                recipient,
                amountWei,
                expiresAt
            )
        );
        if (expectedActionHash != actionHash) revert InvalidAuthorizationCommitment();

        // Mark first; any failed transfer reverts this state change as well.
        consumed[authorizationId] = true;
        // The event and transfer are atomic: a failed transfer reverts this log too.
        emit PaymentExecuted(
            authorizationId,
            recipient,
            issuer,
            amountWei,
            actionHash,
            verigateActionHash,
            policySha256,
            decisionReceiptSha256
        );

        (bool ok, ) = recipient.call{value: amountWei}("");
        if (!ok) revert PaymentTransferFailed(recipient, amountWei);
    }
}
