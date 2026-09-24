// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IVerigateStateOracle {
    /// @dev Returns the state value identified by stateRef. The implementation
    /// must read the canonical state from the same protocol being guarded.
    function readState(bytes32 stateRef) external view returns (bytes32);
}

/// @title VerigateAtomicStateGuard
/// @notice Checks an application-defined state oracle and performs the target
/// call in the same EVM transaction. If the state changed, the whole call
/// reverts and the target side effect is never committed.
contract VerigateAtomicStateGuard {
    error StateMismatch(address oracle, bytes32 stateRef, bytes32 expected, bytes32 actual);
    error StateReadFailed(address oracle, bytes32 stateRef);
    error TargetCallFailed(bytes reason);

    event GuardedExecution(
        address indexed target,
        address indexed oracle,
        bytes32 indexed stateRef,
        bytes32 expected,
        bytes32 actual,
        uint256 value
    );

    function execute(
        address target,
        uint256 value,
        bytes calldata data,
        address oracle,
        bytes32 stateRef,
        bytes32 expected
    ) external payable returns (bytes memory result) {
        bytes32 actual;
        try IVerigateStateOracle(oracle).readState(stateRef) returns (bytes32 observed) {
            actual = observed;
        } catch {
            revert StateReadFailed(oracle, stateRef);
        }
        if (actual != expected) {
            revert StateMismatch(oracle, stateRef, expected, actual);
        }

        (bool ok, bytes memory returned) = target.call{value: value}(data);
        if (!ok) revert TargetCallFailed(returned);
        emit GuardedExecution(target, oracle, stateRef, expected, actual, value);
        return returned;
    }
}
