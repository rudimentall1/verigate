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
/// @dev ACCESS CONTROL. Only the immutable `executor` may call `execute`. The
/// executor must be the account that signs the transactions Verigate's
/// off-chain execution router has authorized (the broadcaster key). Without
/// this check the guard would be a permissionless call relay: anyone could
/// choose the target, the calldata and even a lying oracle, and the call would
/// be made from this contract's address.
///
/// The guard does NOT yet verify a per-action signed authorization on-chain.
/// What the executor sends is only as trustworthy as Verigate's off-chain
/// router and the protection of the executor key. Do not grant this contract
/// any privilege you would not grant to the executor.
contract VerigateAtomicStateGuard {
    /// @notice The only account allowed to call `execute`.
    address public immutable executor;

    error ZeroExecutor();
    error NotExecutor(address caller);
    error ValueMismatch(uint256 value, uint256 sent);
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

    constructor(address executor_) {
        if (executor_ == address(0)) revert ZeroExecutor();
        executor = executor_;
    }

    function execute(
        address target,
        uint256 value,
        bytes calldata data,
        address oracle,
        bytes32 stateRef,
        bytes32 expected
    ) external payable returns (bytes memory result) {
        if (msg.sender != executor) revert NotExecutor(msg.sender);
        // Only the value sent with this call may be forwarded; the guard's own
        // balance can never be spent through execute().
        if (value != msg.value) revert ValueMismatch(value, msg.value);

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
