// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { VerigateOriginAuthorizationHub } from "../src/VerigateOriginAuthorizationHub.sol";

interface VmOrigin {
    function prank(address sender) external;
    function expectRevert() external;
    function expectRevert(bytes4 revertData) external;
}

contract VerigateOriginAuthorizationHubTest {
    VmOrigin private constant vm = VmOrigin(address(uint160(uint256(keccak256("hevm cheat code")))));

    function testOnlyEnabledIssuerCanRegister() external {
        VerigateOriginAuthorizationHub hub = new VerigateOriginAuthorizationHub(address(this));
        bytes32 id = keccak256("auth-1");
        bytes32 actionHash = keccak256("action-1");
        bytes32 policyHash = keccak256("policy-1");
        bytes32 receiptHash = keccak256("receipt-1");

        vm.expectRevert(VerigateOriginAuthorizationHub.NotIssuer.selector);
        vm.prank(address(0xBAD));
        hub.registerAuthorization(
            id,
            actionHash,
            policyHash,
            receiptHash,
            1301,
            address(0xCAFE),
            address(0xBEEF),
            1 ether,
            uint64(block.timestamp + 120)
        );
    }

    function testRegistersExactCommitmentAndRevokesIt() external {
        VerigateOriginAuthorizationHub hub = new VerigateOriginAuthorizationHub(address(this));
        hub.setIssuer(address(this), true);

        bytes32 id = keccak256("auth-2");
        bytes32 actionDigest = keccak256("verigate-action");
        bytes32 policyHash = keccak256("verigate-policy");
        bytes32 receiptHash = keccak256("decision-receipt");
        address recipient = address(0xBEEF);
        address receiver = address(0xCAFE);
        uint256 amountWei = 0.25 ether;
        uint64 expiry = uint64(block.timestamp + 180);

        bytes32 expected = keccak256(
            abi.encode(
                block.chainid,
                address(hub),
                address(this),
                id,
                actionDigest,
                policyHash,
                receiptHash,
                uint256(1301),
                receiver,
                recipient,
                amountWei,
                expiry
            )
        );

        bytes32 returnedHash = hub.registerAuthorization(
            id,
            actionDigest,
            policyHash,
            receiptHash,
            1301,
            receiver,
            recipient,
            amountWei,
            expiry
        );
        require(returnedHash == expected, "origin commitment mismatch");

        (bytes32 storedHash, , , , , , , , , , bool revoked) = hub.authorizations(id);
        require(storedHash == expected, "stored commitment mismatch");
        require(!revoked, "unexpected revoked state");

        hub.revokeAuthorization(id);
        (, , , , , , , , , , revoked) = hub.authorizations(id);
        require(revoked, "revocation was not stored");
    }

    function testOnlyRegisteringIssuerCanRequestExecution() external {
        VerigateOriginAuthorizationHub hub = new VerigateOriginAuthorizationHub(address(this));
        hub.setIssuer(address(this), true);
        bytes32 id = keccak256("auth-requester-bound");

        hub.registerAuthorization(
            id,
            keccak256("action"),
            keccak256("policy"),
            keccak256("receipt"),
            1301,
            address(0xCAFE),
            address(0xBEEF),
            1 ether,
            uint64(block.timestamp + 120)
        );

        vm.expectRevert();
        vm.prank(address(0xBAD));
        hub.requestExecution(
            id,
            address(0xBEEF),
            1 ether,
            1301,
            address(0xCAFE)
        );

        // The same issuer that registered the authorization may submit an
        // execution attempt; Reactive still enforces the committed parameters.
        hub.requestExecution(
            id,
            address(0xBEEF),
            1 ether,
            1301,
            address(0xCAFE)
        );
    }

}
