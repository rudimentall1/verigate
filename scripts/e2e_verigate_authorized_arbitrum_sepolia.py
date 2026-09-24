from __future__ import annotations
import argparse, base64, hashlib, json, os, subprocess, tempfile
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from attest.keys import generate_keypair, load_private_key, load_public_key
from core.engine import GuardrailEngine
from core.evidence import EvidenceGraph
from core.evidence_manifest import build_manifest, verify_manifest
from core.external_state import ExternalStateVerifierRegistry
from core.models import Capability, PaymentIntent
from core.outcome import OutcomeAttestationService, build_outcome_attestation, build_outcome_claim
from core.policy import Policy
from core.storage import Storage
from enforcement.chain_verification import EVMChainVerifier
from enforcement.evm_rpc import EvmRpcClient
from enforcement.external_state import EVMExternalStateVerifier
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter

ROOT=Path(__file__).resolve().parents[1]
def env(name):
    if os.environ.get(name): return os.environ[name]
    for line in (ROOT/".env").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k,v=line.split("=",1)
            if k.strip()==name: return v.strip()
    raise RuntimeError(f"missing {name}")

def node(script,payload):
    p=subprocess.run(["node",str(ROOT/"scripts"/script)],cwd=ROOT,input=json.dumps(payload),
                     text=True,capture_output=True)
    if p.returncode: raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    return json.loads(p.stdout)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--guard",required=True); ap.add_argument("--oracle",required=True); ap.add_argument("--target",required=True)
    a=ap.parse_args()
    rpc=EvmRpcClient(env("ARB_SEPOLIA_RPC"))
    if rpc.chain_id()!=421614: raise RuntimeError("RPC is not Arbitrum Sepolia")
    slot="0x"+"00"*32; state_value=rpc.get_storage_at(a.oracle,slot).lower()
    ref="0x"+hashlib.sha256(b"resource:live-counter").hexdigest()
    target_data="0xd09de08a"
    obs={"kind":"evm.state","chain_id":421614,"address":a.oracle.lower(),"block_tag":"latest",
         "code":rpc.get_code(a.oracle).lower(),"storage":{slot:state_value}}
    state_digest=hashlib.sha256(json.dumps(obs,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    enc=node("encode_atomic_guard.mjs",{"target":a.target,"oracle":a.oracle,"reference":ref,
                                       "expected":state_value,"target_data":target_data})
    state={"kind":"evm.state","reference":"oracle:"+a.oracle.lower(),"digest":state_digest,
           "chain_id":421614,"address":a.oracle,"block_tag":"latest","storage_slots":[slot],
           "atomic_guard":{"address":a.guard,"oracle":a.oracle,"reference":ref,
                           "expected":state_value,"data_sha256":enc["data_sha256"]}}
    tx={"chain_id":421614,"to":a.guard,"value_wei":0,"data":enc["data"]}
    with tempfile.TemporaryDirectory(prefix="verigate-live-") as td:
        root=Path(td); privp=root/"issuer.key"; pubp=root/"issuer.pub"; db=root/"v.db"; pol=root/"policy.yaml"
        generate_keypair(privp,pubp)
        pol.write_text("""allowed_action_types: [payment]
allowed_targets: [live-counter]
allowed_networks: [arbitrum-sepolia]
allowed_assets: [TEST]
external_state_requirements:
  - action_type: payment
    target: live-counter
    kind: evm.state
""",encoding="utf-8")
        st=Storage(db)
        try:
            priv,pub=load_private_key(privp),load_public_key(pubp)
            cap=Capability(capability_id="cap-live-arbitrum",agent_id="verigate-live-agent",
                           allowed_actions=("payment",),allowed_targets=("live-counter",),
                           allowed_networks=("arbitrum-sepolia",),allowed_assets=("TEST",),
                           max_per_action={"TEST":1.0})
            st.register_capability(cap)
            intent=PaymentIntent(agent_id="verigate-live-agent",payee="live-counter",asset="TEST",
                network="arbitrum-sepolia",amount=0.0,
                metadata={"network_family":"evm","evm_transaction":tx,"external_state":state})
            artifacts=GuardrailEngine(Policy.load(pol),st).authorize_with_capability(intent,cap.capability_id,priv)
            auth=artifacts["execution_authorization"]
            if auth is None: raise RuntimeError("ExecutionAuthorization was not issued")
            reg=ExternalStateVerifierRegistry({"evm.state":EVMExternalStateVerifier(rpc)})
            router=ExecutionRouter(NetworkRegistry(),st,pub,private_key=priv,external_state_registry=reg)
            submitted=router.execute_with_receipt(auth,lambda t:node("broadcast_evm.mjs",{"tx":t}),
                                                   executor="verigate-evm-signer")
            if submitted.payload["status"]!="SUBMITTED": raise RuntimeError(submitted.payload.get("error"))
            txh=submitted.payload["transaction_ref"]; confirmation=rpc.confirm_transaction(txh)
            if confirmation["state"]!="CONFIRMED": raise RuntimeError(str(confirmation))
            confirmed=router.confirm_execution_receipt(submitted.as_dict(),confirmation,executor="verigate-evm-signer")
            if confirmed is None or confirmed.payload["status"]!="CONFIRMED": raise RuntimeError("receipt confirmation failed")
            st.update_execution_receipt(confirmed.as_dict())
            observed=EVMChainVerifier().verify_receipt(auth,rpc,transaction_hash=txh,
                                                       evidence_ref=f"arbitrum-sepolia:{txh}")
            if observed.effect_status!="SUCCEEDED": raise RuntimeError(str(observed.as_dict()))
            attp=root/"attestor.key"; atpub=root/"attestor.pub"; generate_keypair(attp,atpub)
            atpriv,atpubkey=load_private_key(attp),load_public_key(atpub)
            atb64=base64.b64encode(atpubkey.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
            svc=OutcomeAttestationService(st,pub)
            svc.register_attestor(attestor_id="live-arbitrum-chain-verifier",public_key_b64=atb64,attestor_type="CHAIN_VERIFIER")
            claim=build_outcome_claim(confirmed.as_dict(),status="SUCCEEDED",executor_id="verigate-evm-signer",
                evidence_kind=observed.evidence_kind,evidence_ref=observed.evidence_ref,result_sha256=observed.result_sha256,
                observed_at=observed.observed_at,metadata={"chain_observation":observed.as_dict()})
            att=build_outcome_attestation(claim,attestor_id="live-arbitrum-chain-verifier",
                attestor_type="CHAIN_VERIFIER",private_key=atpriv,attested_at=observed.observed_at)
            out=svc.verify_and_record(att)
            if not out["valid"] or not out["authority_event"]: raise RuntimeError(str(out))
            graph=EvidenceGraph(st,pub).build(auth["payload"]["authorization_id"])
            manifest=build_manifest(graph,priv,proof_profile="integrity"); check=verify_manifest(manifest)
            if not check["valid"]: raise RuntimeError(str(check))
            print(json.dumps({"ok":True,"chain_id":421614,"authorization_id":auth["payload"]["authorization_id"],
                "intent_id":auth["payload"]["intent_id"],"execution_authorization_issued":True,
                "external_state_verified":True,"execution_boundary":"ExecutionRouter -> EVMExecutionAdapter.execute_bound -> VerigateAtomicStateGuard",
                "transaction_hash":txh,"execution_receipt_status":confirmed.payload["status"],
                "chain_effect_status":observed.effect_status,"chain_evidence_kind":observed.evidence_kind,
                "outcome_attestation_id":out["attestation_id"],"authority_event":out["authority_event"]["event_type"],
                "evidence_nodes":len(graph["nodes"]),"evidence_edges":len(graph["edges"]),
                "evidence_manifest_valid":check["valid"],"evidence_root":check.get("root_digest")},indent=2))
        finally: st.close()
if __name__=="__main__": main()