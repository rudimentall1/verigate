import tempfile
import unittest
from pathlib import Path
from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.authority_state import DynamicAuthorityService
from core.models import ActionIntent, Capability, GuardrailDecision, Decision
from core.policy import Policy
from core.storage import Storage
from enforcement.router import ExecutionRouter
from enforcement.networks import NetworkRegistry

class ExecutionArtifactTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); root=Path(self.tmp.name)
        self.private=root/"k"; self.public=root/"p"; generate_keypair(self.private,self.public)
        self.storage=Storage(root/"db")
    def tearDown(self): self.storage.close(); self.tmp.cleanup()
    def _auth(self, action):
        cap=Capability(capability_id="cap-art",agent_id=action.agent_id,allowed_actions=(action.action_type,),allowed_targets=(action.target,))
        self.storage.register_capability(cap)
        authority=DynamicAuthorityService(self.storage).snapshot(action.agent_id,cap.capability_id)
        d=GuardrailDecision(intent_id=action.intent_id,agent_id=action.agent_id,decision=Decision.ALLOW,matched_rules=())
        return AuthorizationService().issue(action,d,Policy().digest,load_private_key(self.private),nonce=action.intent_id,capability=cap,authority=authority,policy=Policy())["execution_authorization"]
    def test_calldata_drift_is_rejected(self):
        action=ActionIntent(agent_id="a",action_type="token.transfer",target="merchant",network="base",metadata={"evm_transaction":{"chain_id":8453,"to":"0xMerchant","value_wei":0,"data":"0x1234"}})
        auth=self._auth(action)
        auth["payload"]["action"]["metadata"]["evm_transaction"]["data"]="0xdeadbeef"
        ok,reason=__import__("attest.receipt",fromlist=["verify_execution_authorization"]).verify_execution_authorization(auth,load_public_key(self.public))
        self.assertFalse(ok); self.assertIn("authorized action fingerprint",reason)
    def test_authorization_contains_exact_artifact_binding(self):
        action=ActionIntent(agent_id="a",action_type="token.transfer",target="merchant",network="base",metadata={"evm_transaction":{"chain_id":8453,"to":"0xMerchant","value_wei":0,"data":"0x1234"}})
        auth=self._auth(action)
        self.assertEqual(auth["payload"]["execution_artifact"]["kind"], "evm")
        self.assertEqual(len(auth["payload"]["execution_artifact_sha256"]), 64)

    def test_router_blocks_calldata_drift_before_broadcast(self):
        action=ActionIntent(agent_id="a",action_type="token.transfer",target="merchant",network="base",metadata={"evm_transaction":{"chain_id":8453,"to":"0xMerchant","value_wei":0,"data":"0x1234"}})
        auth=self._auth(action); auth["payload"]["action"]["metadata"]["evm_transaction"]["data"]="0xdeadbeef"
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public))
        sent=[]
        with self.assertRaises(ValueError): router.execute(auth,lambda tx: sent.append(tx) or "sent")
        self.assertEqual(sent,[])
if __name__=="__main__": unittest.main()
