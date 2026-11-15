// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

/// @title VerigateOriginAuthorizationHub
/// @notice Origin-chain adapter for publishing a Verigate-verified execution
/// authorization as an immutable, destination-bound commitment.
///
/// SECURITY BOUNDARY:
/// The EVM contract does not verify Verigate's Ed25519 signature. An allowlisted
/// issuer is a bridge attester: it must verify the signed Verigate
/// ExecutionAuthorization off-chain before calling registerAuthorization().
/// The event records the Verigate digests so the decision can be traced.
contract VerigateOriginAuthorizationHub {
    uint64 public constant MAX_AUTHORIZATION_TTL = 300;

    address public owner;
    mapping(address => bool) public issuers;

    struct Authorization {
        bytes32 actionHash;
        bytes32 verigateActionHash;
        bytes32 policySha256;
        bytes32 decisionReceiptSha256;
        address recipient;
        uint256 amountWei;
        uint64 expiresAt;
        uint256 destinationChainId;
        address destinationContract;
        bool revoked;
    }

    mapping(bytes32 => Authorization) public authorizations;

    error NotOwner();
    error NotIssuer();
    error ZeroAddress();
    error InvalidAuthorization();
    error AuthorizationAlreadyRegistered(bytes32 authorizationId);
    error AuthorizationNotFound(bytes32 authorizationId);
    error AlreadyRevoked(bytes32 authorizationId);

    event IssuerUpdated(address indexed issuer, bool enabled);
    event AuthorizationRegistered(
        bytes32 indexed authorizationId,
        bytes32 indexed actionHash,
        address indexed recipient,
        bytes32 verigateActionHash,
        bytes32 policySha256,
        bytes32 decisionReceiptSha256,
        uint256 amountWei,
        uint64 expiresAt,
        uint256 destinationChainId,
        address destinationContract
    );
    event AuthorizationRevoked(bytes32 indexed authorizationId);
    event ExecutionRequested(
        bytes32 indexed authorizationId,
        address indexed recipient,
        uint256 amountWei,
        uint256 destinationChainId,
        address destinationContract
    );

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyIssuer() {
        if (!issuers[msg.sender]) revert NotIssuer();
        _;
    }

    constructor(address owner_) {
        if (owner_ == address(0)) revert ZeroAddress();
        owner = owner_;
    }

    function setIssuer(address issuer, bool enabled) external onlyOwner {
        if (issuer == address(0)) revert ZeroAddress();
        issuers[issuer] = enabled;
        emit IssuerUpdated(issuer, enabled);
    }

    /// @notice Publish a Verigate ALLOW authorization for one exact payment.
    /// @dev The issuer must validate the Ed25519 ExecutionAuthorization and
    ///      map its action fields to these EVM parameters before submitting.
    function registerAuthorization(
        bytes32 authorizationId,
        bytes32 verigateActionHash,
        bytes32 policySha256,
        bytes32 decisionReceiptSha256,
        uint256 destinationChainId,
        address destinationContract,
        address recipient,
        uint256 amountWei,
        uint64 expiresAt
    ) external onlyIssuer returns (bytes32 actionHash) {
        if (
            authorizationId == bytes32(0) ||
            verigateActionHash == bytes32(0) ||
            policySha256 == bytes32(0) ||
            decisionReceiptSha256 == bytes32(0) ||
            destinationChainId == 0 ||
            destinationContract == address(0) ||
            recipient == address(0) ||
            amountWei == 0 ||
            expiresAt <= block.timestamp ||
            uint256(expiresAt) > block.timestamp + MAX_AUTHORIZATION_TTL
        ) revert InvalidAuthorization();

        if (authorizations[authorizationId].actionHash != bytes32(0)) {
            revert AuthorizationAlreadyRegistered(authorizationId);
        }

        actionHash = keccak256(
            abi.encode(
                block.chainid,
                address(this),
                authorizationId,
                verigateActionHash,
                policySha256,
                decisionReceiptSha256,
                destinationChainId,
                destinationContract,
                recipient,
                amountWei,
                expiresAt
            )
        );

        authorizations[authorizationId] = Authorization({
            actionHash: actionHash,
            verigateActionHash: verigateActionHash,
            policySha256: policySha256,
            decisionReceiptSha256: decisionReceiptSha256,
            recipient: recipient,
            amountWei: amountWei,
            expiresAt: expiresAt,
            destinationChainId: destinationChainId,
            destinationContract: destinationContract,
            revoked: false
        });

        emit AuthorizationRegistered(
            authorizationId,
            actionHash,
            recipient,
            verigateActionHash,
            policySha256,
            decisionReceiptSha256,
            amountWei,
            expiresAt,
            destinationChainId,
            destinationContract
        );
    }

    /// @notice Publicly request an execution attempt. Reactive checks every
    ///         supplied field against the cached authorization before callback.
    /// @dev Deliberately permits mismatched fields so rejected attempts produce
    ///      an on-chain ActionBlocked record on the Reactive chain.
    function requestExecution(
        bytes32 authorizationId,
        address recipient,
        uint256 amountWei,
        uint256 destinationChainId,
        address destinationContract
    ) external {
        emit ExecutionRequested(
            authorizationId,
            recipient,
            amountWei,
            destinationChainId,
            destinationContract
        );
    }

    function revokeAuthorization(bytes32 authorizationId) external {
        if (msg.sender != owner && !issuers[msg.sender]) revert NotIssuer();
        Authorization storage auth = authorizations[authorizationId];
        if (auth.actionHash == bytes32(0)) revert AuthorizationNotFound(authorizationId);
        if (auth.revoked) revert AlreadyRevoked(authorizationId);
        auth.revoked = true;
        emit AuthorizationRevoked(authorizationId);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        owner = newOwner;
    }
}
