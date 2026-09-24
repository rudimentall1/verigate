import tempfile, unittest
from pathlib import Path
from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.authority_state import DynamicAuthorityService
from core.models import ActionIntent, Capability, GuardrailDecision, Decision
from core.policy import Policy
from core.storage import Storage
from enforcement.router import ExecutionRouter
from enforcement.networks import NetworkRegistry

class Adapter:
    def execute(self, authorization, side_effect): return side_effect(authorization["payload"]["action"])
    def consume(self, authorization): return True, "ok"

class ExternalStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); root=Path(self.tmp.name)
        self.private=root/'k'; self.public=root/'p'; generate_keypair(self.private,self.public)
        self.storage=Storage(root/'db')
    def tearDown(self): self.storage.close(); self.tmp.cleanup()
    def auth(self, action, policy=None):
        policy=policy or Policy()
        cap=Capability(capability_id='cap-state',agent_id=action.agent_id,allowed_actions=(action.action_type,),allowed_targets=(action.target,))
        self.storage.register_capability(cap)
        authority=DynamicAuthorityService(self.storage).snapshot(action.agent_id,cap.capability_id)
        decision=GuardrailDecision(intent_id=action.intent_id,agent_id=action.agent_id,decision=Decision.ALLOW,matched_rules=())
        return AuthorizationService().issue(action,decision,policy.digest,load_private_key(self.private),nonce=action.intent_id,capability=cap,authority=authority,policy=policy)['execution_authorization']
    def test_required_binding(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders')
        auth=self.auth(action,Policy(require_external_state_binding=True))
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),generic_adapters={'orders.create':Adapter()})
        with self.assertRaises(ValueError): router.execute(auth,lambda a:'side-effect')
    def test_state_drift_before_side_effect(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders',metadata={'external_state':{'kind':'resource.version','reference':'order-1','digest':'b'*64}})
        auth=self.auth(action)
        sent=[]
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),generic_adapters={'orders.create':Adapter()},external_state_verifier=lambda b,a:(False,'reference changed'))
        with self.assertRaises(ValueError): router.execute(auth,lambda a:sent.append(a) or 'bad')
        self.assertEqual(sent,[])
    def test_matching_state_executes(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders',metadata={'external_state':{'kind':'resource.version','reference':'order-1','digest':'b'*64}})
        auth=self.auth(action); sent=[]
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),generic_adapters={'orders.create':Adapter()},external_state_verifier=lambda b,a:(True,'match'))
        self.assertEqual(router.execute(auth,lambda a:sent.append(a) or 'ok'),'ok'); self.assertEqual(len(sent),1)

if __name__=='__main__': unittest.main()
