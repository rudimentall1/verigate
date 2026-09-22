"""Multi-chain network registry for Verigate execution."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from core.storage import Storage
from enforcement.evm import EVMExecutionAdapter
from enforcement.protocol import ExecutionAdapter

@dataclass(frozen=True)
class NetworkDescriptor:
    name: str
    family: str
    chain_id: int | None = None
    native_asset: str | None = None
    execution_supported: bool = False
    aliases: tuple[str, ...] = ()

class UnsupportedNetworkError(ValueError):
    """Raised when Verigate has no execution adapter for a network family."""

DEFAULT_NETWORKS: tuple[NetworkDescriptor, ...] = (
    NetworkDescriptor("ethereum", "evm", 1, "ETH", True, ("mainnet", "eth")),
    NetworkDescriptor("base", "evm", 8453, "ETH", True),
    NetworkDescriptor("arbitrum", "evm", 42161, "ETH", True, ("arbitrum-one",)),
    NetworkDescriptor("optimism", "evm", 10, "ETH", True, ("op",)),
    NetworkDescriptor("polygon", "evm", 137, "POL", True, ("matic",)),
    NetworkDescriptor("bnb-smart-chain", "evm", 56, "BNB", True, ("bsc", "bnb")),
    NetworkDescriptor("avalanche", "evm", 43114, "AVAX", True, ("avax", "c-chain")),
    NetworkDescriptor("linea", "evm", 59144, "ETH", True),
    NetworkDescriptor("zksync-era", "evm", 324, "ETH", True, ("zksync",)),
    NetworkDescriptor("arc", "evm", 5042, "USDC", True),
    NetworkDescriptor("solana", "solana", None, "SOL", False, ("sol",)),
)

class NetworkRegistry:
    """Resolve networks and select the matching execution adapter."""
    def __init__(self, networks: tuple[NetworkDescriptor, ...] = DEFAULT_NETWORKS):
        self._by_name: dict[str, NetworkDescriptor] = {}
        self._by_chain_id: dict[int, NetworkDescriptor] = {}
        for network in networks:
            self.register(network)

    def register(self, network: NetworkDescriptor) -> None:
        for value in (network.name, *network.aliases):
            self._by_name[value.strip().lower()] = network
        if network.chain_id is not None:
            self._by_chain_id[network.chain_id] = network

    def resolve(self, network: str | int) -> NetworkDescriptor:
        if isinstance(network, int):
            try:
                return self._by_chain_id[network]
            except KeyError as exc:
                raise UnsupportedNetworkError(f"unknown chain_id={network}") from exc
        try:
            return self._by_name[network.strip().lower()]
        except KeyError as exc:
            raise UnsupportedNetworkError(f"unknown network: {network}") from exc

    def resolve_evm_chain(self, chain_id: int, *, name: str | None = None) -> NetworkDescriptor:
        if not isinstance(chain_id, int) or chain_id <= 0:
            raise ValueError("chain_id must be a positive integer")
        known = self._by_chain_id.get(chain_id)
        if known is not None:
            return known
        return NetworkDescriptor(name or f"evm-{chain_id}", "evm", chain_id, None, True)

    def adapter(self, network: str | int, storage: Storage, public_key: Ed25519PublicKey) -> ExecutionAdapter:
        descriptor = self.resolve(network)
        if descriptor.family == "evm" and descriptor.execution_supported:
            return EVMExecutionAdapter(storage, public_key)
        raise UnsupportedNetworkError(f"no execution adapter for {descriptor.name} ({descriptor.family})")

    def evm_adapter(self, chain_id: int, storage: Storage, public_key: Ed25519PublicKey) -> EVMExecutionAdapter:
        descriptor = self.resolve_evm_chain(chain_id)
        if descriptor.family != "evm":
            raise UnsupportedNetworkError(f"chain_id={chain_id} is not EVM")
        return EVMExecutionAdapter(storage, public_key)

    def as_dict(self) -> list[dict[str, Any]]:
        unique = {id(network): network for network in self._by_name.values()}
        return [
            {
                "name": network.name,
                "family": network.family,
                "chain_id": network.chain_id,
                "native_asset": network.native_asset,
                "execution_supported": network.execution_supported,
                "aliases": list(network.aliases),
            }
            for network in sorted(unique.values(), key=lambda item: item.name)
        ]
