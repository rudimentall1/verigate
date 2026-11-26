// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Verigate Authority Registry
/// @notice On-chain registry for signed off-chain Verigate authorizations.
contract VerigateAuthorityRegistry {
    address public owner;

    struct Authorization {
        bytes32 intentHash;
        address executor;
        uint64 validUntil;
        uint64 registeredAt;
        bool consumed;
        bool revoked;
    }

    mapping(address => bool) public issuers;
    mapping(bytes32 => Authorization) public authorizations;

    event IssuerUpdated(address indexed issuer, bool enabled);

    event AuthorizationRegistered(
        bytes32 indexed authorizationId,
        bytes32 indexed intentHash,
        address indexed executor,
        uint64 validUntil,
        address issuer
    );

    event AuthorizationConsumed(
        bytes32 indexed authorizationId,
        bytes32 indexed intentHash,
        address indexed executor
    );

    event AuthorizationRevoked(
        bytes32 indexed authorizationId,
        address indexed issuer
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier onlyIssuer() {
        require(issuers[msg.sender], "Not authorized issuer");
        _;
    }

    constructor() {
        owner = msg.sender;
        issuers[msg.sender] = true;
        emit IssuerUpdated(msg.sender, true);
    }

    function setIssuer(address issuer, bool enabled) external onlyOwner {
        require(issuer != address(0), "Zero issuer");
        issuers[issuer] = enabled;
        emit IssuerUpdated(issuer, enabled);
    }

    function registerAuthorization(
        bytes32 authorizationId,
        bytes32 intentHash,
        address executor,
        uint64 validUntil
    ) external onlyIssuer {
        require(authorizationId != bytes32(0), "Empty authorization ID");
        require(intentHash != bytes32(0), "Empty intent hash");
        require(executor != address(0), "Zero executor");
        require(validUntil > block.timestamp, "Already expired");
        require(
            authorizations[authorizationId].registeredAt == 0,
            "Authorization already exists"
        );

        authorizations[authorizationId] = Authorization({
            intentHash: intentHash,
            executor: executor,
            validUntil: validUntil,
            registeredAt: uint64(block.timestamp),
            consumed: false,
            revoked: false
        });

        emit AuthorizationRegistered(
            authorizationId,
            intentHash,
            executor,
            validUntil,
            msg.sender
        );
    }

    function consumeAuthorization(
        bytes32 authorizationId,
        bytes32 intentHash
    ) external {
        Authorization storage auth = authorizations[authorizationId];

        require(auth.registeredAt != 0, "Unknown authorization");
        require(!auth.revoked, "Authorization revoked");
        require(!auth.consumed, "Already consumed");
        require(block.timestamp <= auth.validUntil, "Authorization expired");
        require(msg.sender == auth.executor, "Wrong executor");
        require(intentHash == auth.intentHash, "Intent hash mismatch");

        auth.consumed = true;

        emit AuthorizationConsumed(
            authorizationId,
            intentHash,
            msg.sender
        );
    }

    function revokeAuthorization(bytes32 authorizationId) external {
        require(
            msg.sender == owner || issuers[msg.sender],
            "Not authorized to revoke"
        );

        Authorization storage auth = authorizations[authorizationId];

        require(auth.registeredAt != 0, "Unknown authorization");
        require(!auth.consumed, "Already consumed");
        require(!auth.revoked, "Already revoked");

        auth.revoked = true;
        emit AuthorizationRevoked(authorizationId, msg.sender);
    }

    function getAuthorization(
        bytes32 authorizationId
    ) external view returns (Authorization memory) {
        return authorizations[authorizationId];
    }
}
