// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { ISystemContract } from "@reactive/src/interfaces/ISystemContract.sol";
import { IReactive } from "@reactive/src/interfaces/IReactive.sol";
import { AbstractReactive } from "@reactive/src/base/AbstractReactive.sol";

interface IVerigatePaymentCallback {
    function executeAuthorizedPayment(
        address reactive_,
        bytes32 authorizationId,
        address payable recipient,
        uint256 amountWei,
        uint64 expiresAt,
        bytes32 actionHash,
        bytes32 verigateActionHash,
        bytes32 policySha256,
        bytes32 decisionReceiptSha256
    ) external;
}

/// @title VerigateReactiveGuard
/// @notice Caches issuer-published Verigate commitments and gates destination
///         callbacks on exact recipient, amount, chain, contract, expiry,
///         revocation and one-time-use checks.
contract VerigateReactiveGuard is AbstractReactive {
    uint256 private constant AUTHORIZATION_REGISTERED_TOPIC0 = uint256(
        keccak256(
            "AuthorizationRegistered(bytes32,bytes32,address,bytes32,bytes32,bytes32,uint256,uint64,uint256,address)"
        )
    );
    uint256 private constant AUTHORIZATION_REVOKED_TOPIC0 = uint256(
        keccak256("AuthorizationRevoked(bytes32)")
    );
    uint256 private constant EXECUTION_REQUESTED_TOPIC0 = uint256(
        keccak256("ExecutionRequested(bytes32,address,uint256,uint256,address)")
    );

    uint64 public constant MIN_CALLBACK_GAS = 100_000;

    uint8 public constant BLOCK_UNKNOWN_AUTHORIZATION = 1;
    uint8 public constant BLOCK_REVOKED = 2;
    uint8 public constant BLOCK_ALREADY_CONSUMED = 3;
    uint8 public constant BLOCK_EXPIRED = 4;
    uint8 public constant BLOCK_ACTION_MISMATCH = 5;
    uint8 public constant BLOCK_DESTINATION_NOT_CONFIGURED = 6;
    uint8 public constant BLOCK_COMMITMENT_MISMATCH = 7;

    uint8 private constant REGISTER_REJECT_DUPLICATE = 1;
    uint8 private constant REGISTER_REJECT_DESTINATION_UNSET = 2;
    uint8 private constant REGISTER_REJECT_DESTINATION_MISMATCH = 3;
    uint8 private constant REGISTER_REJECT_INVALID_FIELDS = 4;
    uint8 private constant REGISTER_REJECT_COMMITMENT = 5;

    address public owner;
    uint256 public immutable originChainId;
    address public immutable originHub;
    uint256 public immutable destinationChainId;
    uint64 public immutable callbackGasLimit;
    address public destinationReceiver;

    struct CachedAuthorization {
        bytes32 actionHash;
        bytes32 verigateActionHash;
        bytes32 policySha256;
        bytes32 decisionReceiptSha256;
        address recipient;
        uint256 amountWei;
        uint64 expiresAt;
        uint256 destinationChainId;
        address destinationContract;
        bool exists;
        bool revoked;
        bool consumed;
    }

    mapping(bytes32 => CachedAuthorization) private _authorizations;

    error NotOwner();
    error InvalidConfiguration();
    error DestinationAlreadyConfigured();

    event DestinationReceiverConfigured(address indexed receiver);
    event AuthorizationCached(bytes32 indexed authorizationId, bytes32 indexed actionHash);
    event AuthorizationRegistrationRejected(bytes32 indexed authorizationId, uint8 reasonCode);
    event AuthorizationRevocationObserved(bytes32 indexed authorizationId);
    event ActionAllowed(
        bytes32 indexed authorizationId,
        address indexed recipient,
        uint256 amountWei,
        bytes32 actionHash,
        uint256 destinationChainId,
        address destinationReceiver
    );
    event ActionBlocked(
        bytes32 indexed authorizationId,
        address indexed requestedRecipient,
        uint256 requestedAmountWei,
        uint8 reasonCode
    );

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(
        uint256 originChainId_,
        address originHub_,
        uint256 destinationChainId_,
        uint64 callbackGasLimit_
    ) payable {
        if (
            originChainId_ == 0 ||
            originHub_ == address(0) ||
            destinationChainId_ == 0 ||
            callbackGasLimit_ < MIN_CALLBACK_GAS
        ) revert InvalidConfiguration();

        owner = msg.sender;
        originChainId = originChainId_;
        originHub = originHub_;
        destinationChainId = destinationChainId_;
        callbackGasLimit = callbackGasLimit_;

        SYSTEM.subscribe(
            originChainId_,
            originHub_,
            AUTHORIZATION_REGISTERED_TOPIC0,
            REACTIVE_IGNORE,
            REACTIVE_IGNORE,
            REACTIVE_IGNORE
        );
        SYSTEM.subscribe(
            originChainId_,
            originHub_,
            AUTHORIZATION_REVOKED_TOPIC0,
            REACTIVE_IGNORE,
            REACTIVE_IGNORE,
            REACTIVE_IGNORE
        );
        SYSTEM.subscribe(
            originChainId_,
            originHub_,
            EXECUTION_REQUESTED_TOPIC0,
            REACTIVE_IGNORE,
            REACTIVE_IGNORE,
            REACTIVE_IGNORE
        );
    }

    /// @notice Set once, after the destination callback contract is deployed
    ///         with this Reactive contract as its immutable callback sender.
    function setDestinationReceiver(address receiver) external onlyOwner {
        if (receiver == address(0)) revert InvalidConfiguration();
        if (destinationReceiver != address(0)) revert DestinationAlreadyConfigured();
        destinationReceiver = receiver;
        emit DestinationReceiverConfigured(receiver);
    }

    /// @inheritdoc IReactive
    function react(IReactive.LogRecord calldata log_) external override onlySystem {
        if (log_.chainId != originChainId || log_.contractAddress != originHub) return;

        if (log_.topic0 == AUTHORIZATION_REGISTERED_TOPIC0) {
            if (log_.opCode != 4) return;
            _handleAuthorizationRegistered(log_);
            return;
        }

        if (log_.topic0 == AUTHORIZATION_REVOKED_TOPIC0) {
            if (log_.opCode != 2) return;
            _handleAuthorizationRevoked(log_);
            return;
        }

        if (log_.topic0 == EXECUTION_REQUESTED_TOPIC0) {
            if (log_.opCode != 3) return;
            _handleExecutionRequested(log_);
        }
    }

    function getAuthorization(bytes32 authorizationId)
        external
        view
        returns (CachedAuthorization memory)
    {
        return _authorizations[authorizationId];
    }

    function _handleAuthorizationRegistered(IReactive.LogRecord calldata log_) internal {
        bytes32 authorizationId = bytes32(log_.topic1);
        bytes32 actionHash = bytes32(log_.topic2);
        address recipient = address(uint160(log_.topic3));

        (
            bytes32 verigateActionHash,
            bytes32 policySha256,
            bytes32 decisionReceiptSha256,
            uint256 amountWei,
            uint64 expiresAt,
            uint256 destinationChainId_,
            address destinationContract
        ) = abi.decode(
            log_.data,
            (bytes32, bytes32, bytes32, uint256, uint64, uint256, address)
        );

        if (_authorizations[authorizationId].exists) {
            emit AuthorizationRegistrationRejected(authorizationId, REGISTER_REJECT_DUPLICATE);
            return;
        }
        if (destinationReceiver == address(0)) {
            emit AuthorizationRegistrationRejected(
                authorizationId,
                REGISTER_REJECT_DESTINATION_UNSET
            );
            return;
        }
        if (
            destinationChainId_ != destinationChainId ||
            destinationContract != destinationReceiver
        ) {
            emit AuthorizationRegistrationRejected(
                authorizationId,
                REGISTER_REJECT_DESTINATION_MISMATCH
            );
            return;
        }
        if (recipient == address(0) || amountWei == 0 || expiresAt <= block.timestamp) {
            emit AuthorizationRegistrationRejected(
                authorizationId,
                REGISTER_REJECT_INVALID_FIELDS
            );
            return;
        }

        bytes32 expectedActionHash = _computeActionHash(
            authorizationId,
            verigateActionHash,
            policySha256,
            decisionReceiptSha256,
            destinationChainId_,
            destinationContract,
            recipient,
            amountWei,
            expiresAt
        );
        if (actionHash != expectedActionHash) {
            emit AuthorizationRegistrationRejected(
                authorizationId,
                REGISTER_REJECT_COMMITMENT
            );
            return;
        }

        _authorizations[authorizationId] = CachedAuthorization({
            actionHash: actionHash,
            verigateActionHash: verigateActionHash,
            policySha256: policySha256,
            decisionReceiptSha256: decisionReceiptSha256,
            recipient: recipient,
            amountWei: amountWei,
            expiresAt: expiresAt,
            destinationChainId: destinationChainId_,
            destinationContract: destinationContract,
            exists: true,
            revoked: false,
            consumed: false
        });

        emit AuthorizationCached(authorizationId, actionHash);
    }

    function _handleAuthorizationRevoked(IReactive.LogRecord calldata log_) internal {
        bytes32 authorizationId = bytes32(log_.topic1);
        CachedAuthorization storage auth = _authorizations[authorizationId];
        if (!auth.exists) return;
        auth.revoked = true;
        emit AuthorizationRevocationObserved(authorizationId);
    }

    function _handleExecutionRequested(IReactive.LogRecord calldata log_) internal {
        bytes32 authorizationId = bytes32(log_.topic1);
        address requestedRecipient = address(uint160(log_.topic2));
        (
            uint256 requestedAmountWei,
            uint256 requestedDestinationChainId,
            address requestedDestinationContract
        ) = abi.decode(log_.data, (uint256, uint256, address));

        CachedAuthorization storage auth = _authorizations[authorizationId];

        if (!auth.exists) {
            _block(authorizationId, requestedRecipient, requestedAmountWei, BLOCK_UNKNOWN_AUTHORIZATION);
            return;
        }
        if (auth.revoked) {
            _block(authorizationId, requestedRecipient, requestedAmountWei, BLOCK_REVOKED);
            return;
        }
        if (auth.consumed) {
            _block(authorizationId, requestedRecipient, requestedAmountWei, BLOCK_ALREADY_CONSUMED);
            return;
        }
        if (auth.expiresAt <= block.timestamp) {
            _block(authorizationId, requestedRecipient, requestedAmountWei, BLOCK_EXPIRED);
            return;
        }
        if (
            requestedRecipient != auth.recipient ||
            requestedAmountWei != auth.amountWei ||
            requestedDestinationChainId != auth.destinationChainId ||
            requestedDestinationContract != auth.destinationContract
        ) {
            _block(authorizationId, requestedRecipient, requestedAmountWei, BLOCK_ACTION_MISMATCH);
            return;
        }
        if (auth.destinationContract != destinationReceiver || destinationReceiver == address(0)) {
            _block(
                authorizationId,
                requestedRecipient,
                requestedAmountWei,
                BLOCK_DESTINATION_NOT_CONFIGURED
            );
            return;
        }

        bytes32 expectedActionHash = _computeActionHash(
            authorizationId,
            auth.verigateActionHash,
            auth.policySha256,
            auth.decisionReceiptSha256,
            auth.destinationChainId,
            auth.destinationContract,
            auth.recipient,
            auth.amountWei,
            auth.expiresAt
        );
        if (auth.actionHash != expectedActionHash) {
            _block(
                authorizationId,
                requestedRecipient,
                requestedAmountWei,
                BLOCK_COMMITMENT_MISMATCH
            );
            return;
        }

        // Effects before interaction. If requesting the callback reverts, this
        // Reactive transaction reverts too and the authorization remains unused.
        auth.consumed = true;

        bytes memory payload = abi.encodeWithSelector(
            IVerigatePaymentCallback.executeAuthorizedPayment.selector,
            address(0), // Reactive injects its own address into the first 160 bits.
            authorizationId,
            auth.recipient,
            auth.amountWei,
            auth.expiresAt,
            auth.actionHash,
            auth.verigateActionHash,
            auth.policySha256,
            auth.decisionReceiptSha256
        );

        // If the system contract rejects the callback request, this log and the
        // consumed state revert atomically with the Reactive transaction.
        emit ActionAllowed(
            authorizationId,
            auth.recipient,
            auth.amountWei,
            auth.actionHash,
            destinationChainId,
            destinationReceiver
        );

        SYSTEM.requestCallbackV_1_0(
            ISystemContract.CallbackConfiguration_V_1_0({
                chainId: destinationChainId,
                recipient: destinationReceiver,
                gasLimit: callbackGasLimit,
                payload: payload
            })
        );
    }

    function _block(
        bytes32 authorizationId,
        address requestedRecipient,
        uint256 requestedAmountWei,
        uint8 reasonCode
    ) internal {
        emit ActionBlocked(
            authorizationId,
            requestedRecipient,
            requestedAmountWei,
            reasonCode
        );
    }

    function _computeActionHash(
        bytes32 authorizationId,
        bytes32 verigateActionHash,
        bytes32 policySha256,
        bytes32 decisionReceiptSha256,
        uint256 destinationChainId_,
        address destinationContract,
        address recipient,
        uint256 amountWei,
        uint64 expiresAt
    ) internal view returns (bytes32) {
        return keccak256(
            abi.encode(
                originChainId,
                originHub,
                authorizationId,
                verigateActionHash,
                policySha256,
                decisionReceiptSha256,
                destinationChainId_,
                destinationContract,
                recipient,
                amountWei,
                expiresAt
            )
        );
    }
}
