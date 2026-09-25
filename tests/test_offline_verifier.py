import hashlib
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from attest.receipt import issue_execution_authorization, sign_receipt
from core.models import ActionIntent, GuardrailDecision, Decision
from core.evidence_manifest import build_manifest
from core.offline_verifier import verify_authority_ledger, verify_proof, _check_authority_binding
from core.proof_engine import canonical

def node(kind, ident, data):
    return {"type": kind, "id": ident, "sha256": hashlib.sha256(canonical(data)).hexdigest(), "data": data}

class OfflineVerifierTests(unittest.TestCase):
    def test_integrity_manifest_verifies_without_runtime(self):
        key = Ed25519PrivateKey.generate()
        graph = {"authorization_id":"auth-1","intent_id":"intent-1","agent_id":"agent-1","graph_version":1,
                 "nodes":[node("action_intent","intent-1",{"intent_id":"intent-1"})],"edges":[],"verification":{},"audit":{}}
        result = verify_proof(build_manifest(graph,key))
        self.assertTrue(result["valid"])

    def test_ledger_chain_is_verified_locally(self):
        event1={"event_id":"e1","agent_id":"a","capability_id":"c","event_type":"CREATED"}
        h1=hashlib.sha256(canonical(event1)).hexdigest()
        event2={"event_id":"e2","agent_id":"a","capability_id":"c","event_type":"SUCCESS"}
        h2=hashlib.sha256(canonical(event2)).hexdigest()
        entries=[{"sequence":1,"event_id":"e1","prev_event_hash":"0"*64,"event_hash":h1,"event":event1},
                 {"sequence":2,"event_id":"e2","prev_event_hash":h1,"event_hash":h2,"event":event2}]
        ok,reason,head=verify_authority_ledger(entries)
        self.assertTrue(ok); self.assertEqual(reason,"valid"); self.assertEqual(head,h2)
        entries[1]["event"]["event_type"]="TAMPERED"
        ok,reason,_=verify_authority_ledger(entries)
        self.assertFalse(ok); self.assertEqual(reason,"authority ledger event digest mismatch")

    def _authorized_graph(self, committed_head):
        key=Ed25519PrivateKey.generate()
        intent=ActionIntent(agent_id="agent-1",action_type="data.write",target="db:item")
        decision=GuardrailDecision(intent.intent_id,intent.agent_id,Decision.ALLOW,tuple(),intent.context_digest)
        receipt=sign_receipt(intent,decision,"a"*64,key)
        event={"event_id":"e1","agent_id":"agent-1","capability_id":"cap-1","event_type":"EXECUTION_CONFIRMED"}
        head=hashlib.sha256(canonical(event)).hexdigest()
        state={"state":"STANDARD","ledger_head_hash":head}
        state_hash=hashlib.sha256(canonical(state)).hexdigest()
        auth=issue_execution_authorization(receipt,key,nonce="n1",capability_id="cap-1",capability_sha256="c"*64,
            authority_state=state,authority_state_sha256=state_hash,authority_multiplier=1.0,
            effective_authority={"action_type":["data.write"],"target":["db:item"]}, execution_graph={"module":"test","hook":"test","router":"test","target":"db:item"},
            authority_ledger_head_hash=head).as_dict()
        ledger=[{"sequence":1,"event_id":"e1","prev_event_hash":"0"*64,"event_hash":head,"event":event}]
        graph={"authorization_id":auth["payload"]["authorization_id"],"intent_id":intent.intent_id,"agent_id":intent.agent_id,"graph_version":1,
          "nodes":[node("action_intent",intent.intent_id,intent.as_dict()),node("execution_authorization",auth["payload"]["authorization_id"],auth),
                   node("authority_ledger","agent-1:cap-1",{"agent_id":"agent-1","capability_id":"cap-1","entries":ledger})],
          "edges":[],"verification":{},"audit":{},
          "historical_authority":{"valid":True,"reason":"historical authority decision verified","details":{"ledger_head_hash":head,"head_match":True,"ledger_sequence":1}}}
        return key,graph,head

    def test_execution_authorization_and_historical_head_are_verified(self):
        key,graph,head=self._authorized_graph("ignored")
        result=verify_proof(build_manifest(graph,key))
        self.assertTrue(result["valid"],result)
        self.assertTrue(result["checks"]["execution_authorization"]["valid"])
        self.assertTrue(result["checks"]["historical_authority"]["valid"])

    def test_committed_ledger_head_mismatch_is_rejected(self):
        key,graph,head=self._authorized_graph("ignored")
        graph["nodes"][1]["data"]["payload"]["authority_ledger_head_hash"]="b"*64
        ok,reason,_=_check_authority_binding(build_manifest(graph,key)["payload"])
        self.assertFalse(ok)
        self.assertEqual(reason,"historical authority ledger head mismatch")


if __name__=="__main__":
    unittest.main()
