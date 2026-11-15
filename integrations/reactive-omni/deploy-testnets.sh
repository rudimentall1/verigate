#!/usr/bin/env bash
set -Eeuo pipefail

# Deploy the three-contract Reactive demo to Base Sepolia, Lasna and
# Unichain Sepolia. Private keys are read only from the caller's environment.
# The script never writes keys to disk or prints them.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

readonly REACTIVE_LIB_COMMIT="3ade0dcf1d27e67e5783ef807e73a1b9e0c0cce8"
readonly BASE_SEPOLIA_CHAIN_ID="84532"
readonly LASNA_CHAIN_ID="5318007"
readonly UNICHAIN_SEPOLIA_CHAIN_ID="1301"
readonly UNICHAIN_CALLBACK_PROXY="0x775c9B990ADe401060B78D0e98684eEf8d2466C1"
readonly CALLBACK_GAS_LIMIT="${CALLBACK_GAS_LIMIT:-200000}"

for bin in forge cast git sed; do
  command -v "$bin" >/dev/null 2>&1 || {
    echo "Missing required command: $bin" >&2
    exit 1
  }
done

: "${BASE_SEPOLIA_RPC_URL:?Set BASE_SEPOLIA_RPC_URL}"
: "${LASNA_RPC_URL:?Set LASNA_RPC_URL}"
: "${UNICHAIN_SEPOLIA_RPC_URL:?Set UNICHAIN_SEPOLIA_RPC_URL}"
: "${DEPLOYER_PRIVATE_KEY:?Set DEPLOYER_PRIVATE_KEY (testnet only)}"
: "${ISSUER_PRIVATE_KEY:?Set ISSUER_PRIVATE_KEY for the Verigate bridge issuer (testnet only)}"

if ! [[ "$CALLBACK_GAS_LIMIT" =~ ^[0-9]+$ ]] || (( CALLBACK_GAS_LIMIT < 100000 )); then
  echo "CALLBACK_GAS_LIMIT must be an integer >= 100000" >&2
  exit 1
fi

ADMIN_ADDRESS="$(cast wallet address --private-key "$DEPLOYER_PRIVATE_KEY")"
ISSUER_ADDRESS="$(cast wallet address --private-key "$ISSUER_PRIVATE_KEY")"

assert_chain() {
  local label="$1" rpc="$2" expected="$3"
  local actual
  actual="$(cast chain-id --rpc-url "$rpc")"
  if [[ "$actual" != "$expected" ]]; then
    echo "$label chain ID mismatch: expected $expected, received $actual" >&2
    exit 1
  fi
  printf '%s chain verified: %s\n' "$label" "$actual"
}

assert_chain "Base Sepolia" "$BASE_SEPOLIA_RPC_URL" "$BASE_SEPOLIA_CHAIN_ID"
assert_chain "Lasna" "$LASNA_RPC_URL" "$LASNA_CHAIN_ID"
assert_chain "Unichain Sepolia" "$UNICHAIN_SEPOLIA_RPC_URL" "$UNICHAIN_SEPOLIA_CHAIN_ID"

if [[ ! -d "lib/reactive-lib-omni/.git" ]]; then
  git clone https://github.com/Reactive-Network/reactive-lib-omni.git lib/reactive-lib-omni
fi
git -C lib/reactive-lib-omni checkout "$REACTIVE_LIB_COMMIT" >/dev/null
ACTUAL_LIB_COMMIT="$(git -C lib/reactive-lib-omni rev-parse HEAD)"
if [[ "$ACTUAL_LIB_COMMIT" != "$REACTIVE_LIB_COMMIT" ]]; then
  echo "Reactive library revision mismatch: $ACTUAL_LIB_COMMIT" >&2
  exit 1
fi

extract_address() {
  sed -nE 's/^Deployed to: (0x[0-9a-fA-F]{40})$/\1/p' | tail -n 1
}

deploy() {
  local label="$1" rpc="$2" contract="$3"
  shift 3
  local output address
  echo "Deploying $label..." >&2
  output="$(forge create --broadcast \
    --rpc-url "$rpc" \
    --private-key "$DEPLOYER_PRIVATE_KEY" \
    "$contract" \
    --constructor-args "$@" 2>&1)" || {
      printf '%s\n' "$output" >&2
      echo "$label deployment failed" >&2
      exit 1
    }
  printf '%s\n' "$output" >&2
  address="$(printf '%s\n' "$output" | extract_address)"
  if [[ ! "$address" =~ ^0x[0-9a-fA-F]{40}$ ]]; then
    echo "Could not parse deployed address for $label; inspect forge output above." >&2
    exit 1
  fi
  printf '%s' "$address"
}

ORIGIN_HUB="$(deploy "Origin Authorization Hub" "$BASE_SEPOLIA_RPC_URL" \
  "src/VerigateOriginAuthorizationHub.sol:VerigateOriginAuthorizationHub" \
  "$ADMIN_ADDRESS")"

REACTIVE_GUARD="$(deploy "Reactive Guard" "$LASNA_RPC_URL" \
  "src/VerigateReactiveGuard.sol:VerigateReactiveGuard" \
  "$BASE_SEPOLIA_CHAIN_ID" "$ORIGIN_HUB" "$UNICHAIN_SEPOLIA_CHAIN_ID" "$CALLBACK_GAS_LIMIT")"

DESTINATION_RECEIVER="$(deploy "Destination Payment Receiver" "$UNICHAIN_SEPOLIA_RPC_URL" \
  "src/VerigatePaymentReceiver.sol:VerigatePaymentReceiver" \
  "$UNICHAIN_CALLBACK_PROXY" "$REACTIVE_GUARD" "$BASE_SEPOLIA_CHAIN_ID" "$ORIGIN_HUB")"

echo "Enabling bridge issuer $ISSUER_ADDRESS on the origin hub..." >&2
cast send --rpc-url "$BASE_SEPOLIA_RPC_URL" \
  --private-key "$DEPLOYER_PRIVATE_KEY" \
  "$ORIGIN_HUB" "setIssuer(address,bool)" "$ISSUER_ADDRESS" true >/dev/null

echo "Setting destination receiver on the Reactive Guard..." >&2
cast send --rpc-url "$LASNA_RPC_URL" \
  --private-key "$DEPLOYER_PRIVATE_KEY" \
  "$REACTIVE_GUARD" "setDestinationReceiver(address)" "$DESTINATION_RECEIVER" >/dev/null

if [[ -n "${REACTIVE_TOPUP_WEI:-}" ]]; then
  echo "Funding Reactive Guard with configured native-token top-up..." >&2
  cast send --rpc-url "$LASNA_RPC_URL" --private-key "$DEPLOYER_PRIVATE_KEY" \
    --value "$REACTIVE_TOPUP_WEI" "$REACTIVE_GUARD" >/dev/null
fi

if [[ -n "${RECEIVER_TOPUP_WEI:-}" ]]; then
  echo "Funding destination receiver with configured native-token top-up..." >&2
  cast send --rpc-url "$UNICHAIN_SEPOLIA_RPC_URL" --private-key "$DEPLOYER_PRIVATE_KEY" \
    --value "$RECEIVER_TOPUP_WEI" "$DESTINATION_RECEIVER" >/dev/null
fi

cat <<SUMMARY
{
  "status": "DEPLOYED_BY_SCRIPT",
  "networks": {
    "origin": {"name": "Base Sepolia", "chain_id": $BASE_SEPOLIA_CHAIN_ID, "hub": "$ORIGIN_HUB"},
    "reactive": {"name": "Lasna", "chain_id": $LASNA_CHAIN_ID, "guard": "$REACTIVE_GUARD"},
    "destination": {"name": "Unichain Sepolia", "chain_id": $UNICHAIN_SEPOLIA_CHAIN_ID, "receiver": "$DESTINATION_RECEIVER", "callback_proxy": "$UNICHAIN_CALLBACK_PROXY"}
  },
  "issuer": "$ISSUER_ADDRESS",
  "callback_gas_limit": $CALLBACK_GAS_LIMIT,
  "reactive_library_commit": "$REACTIVE_LIB_COMMIT"
}
SUMMARY

echo "Deployment complete. Independently verify all three addresses and receipts before using them in a submission." >&2
