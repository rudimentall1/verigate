import tempfile, unittest
from pathlib import Path
from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.authority_state import DynamicAuthorityService
from core.models import ActionIntent, Capability, GuardrailDecision, Decision
from core.policy import Policy
from core.external_state import ExternalStateVerifierRegistry
from core.storage import Storage
from enforcement.router import ExecutionRouter
from enforcement.networks import NetworkRegistry
from core.proof_validators.common import validate_external_state_execution_scope

class Adapter:
    def validate(self, authorization): return True, "validated"
    def execute_after_consume(self, authorization, side_effect): return side_effect(authorization["payload"]["action"])
    def execute(self, authorization, side_effect):
        self.consume(authorization)
        return self.execute_after_consume(authorization, side_effect)
    def consume(self, authorization): return True, "ok"

class BoundAdapter(Adapter):
    execution_external_state_scope = "atomic"

    def execute_bound_after_consume(self, authorization, external_state, side_effect):
        # Test adapter models an execution backend that atomically binds the
        # state precondition before the side effect.
        assert external_state == authorization["payload"]["external_state"]
        return side_effect(authorization["payload"]["action"])

    def execute_bound(self, authorization, external_state, side_effect):
        self.consume(authorization)
        return self.execute_bound_after_consume(authorization, external_state, side_effect)

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

    def test_policy_requirement_is_bound_to_authorization(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders')
        policy=Policy(external_state_requirements=[{'action_type':'orders.create','target':'orders','kind':'http.state'}])
        auth=self.auth(action,policy)
        self.assertTrue(auth['payload']['external_state_required'])
        self.assertEqual(auth['payload']['external_state_requirement']['kind'],'http.state')
        self.assertEqual(len(auth['payload']['external_state_requirement_sha256']),64)

    def test_required_kind_blocks_missing_binding(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders')
        policy=Policy(external_state_requirements=[{'action_type':'orders.create','target':'orders','kind':'http.state'}])
        auth=self.auth(action,policy)
        registry=ExternalStateVerifierRegistry({'http.state': lambda b,a:(True,'ok')})
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),generic_adapters={'orders.create':Adapter()},external_state_registry=registry)
        with self.assertRaises(ValueError): router.execute(auth,lambda a:'side-effect')

    def test_required_kind_mismatch_blocks_before_side_effect(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders',metadata={'external_state':{'kind':'mcp.state','reference':'orders','digest':'b'*64}})
        policy=Policy(external_state_requirements=[{'action_type':'orders.create','target':'orders','kind':'http.state'}])
        auth=self.auth(action,policy); sent=[]
        registry=ExternalStateVerifierRegistry({'mcp.state': lambda b,a:(True,'ok'), 'http.state': lambda b,a:(True,'ok')})
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),generic_adapters={'orders.create':Adapter()},external_state_registry=registry)
        with self.assertRaises(ValueError): router.execute(auth,lambda a:sent.append(a) or 'bad')
        self.assertEqual(sent,[])

    def test_registry_dispatch_executes_valid_required_state(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders',metadata={'external_state':{'kind':'http.state','reference':'orders','digest':'b'*64}})
        policy=Policy(external_state_requirements=[{'action_type':'orders.create','target':'orders','kind':'http.state'}])
        auth=self.auth(action,policy); sent=[]; calls=[]
        registry=ExternalStateVerifierRegistry({'http.state': lambda b,a:calls.append(b['kind']) or (True,'match')})
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),generic_adapters={'orders.create':BoundAdapter()},external_state_registry=registry)
        self.assertEqual(router.execute(auth,lambda a:sent.append(a) or 'ok'),'ok')
        self.assertEqual(calls,['http.state']); self.assertEqual(len(sent),1)

    def test_ambiguous_equal_specificity_requirements_fail_closed(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders')
        policy=Policy(external_state_requirements=[
            {'action_type':'orders.create','target':'orders','kind':'http.state'},
            {'action_type':'orders.create','target':'orders','kind':'mcp.state'},
        ])
        with self.assertRaises(ValueError):
            self.auth(action,policy)

    def test_duplicate_equal_specificity_requirement_is_deterministic(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders')
        policy=Policy(external_state_requirements=[
            {'action_type':'orders.create','target':'orders','kind':'http.state'},
            {'action_type':'orders.create','target':'orders','kind':'http.state'},
        ])
        auth=self.auth(action,policy)
        self.assertEqual(auth['payload']['external_state_requirement']['kind'],'http.state')

    def test_required_state_blocks_non_atomic_adapter(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders',metadata={'external_state':{'kind':'http.state','reference':'orders','digest':'b'*64}})
        policy=Policy(external_state_requirements=[{'action_type':'orders.create','target':'orders','kind':'http.state'}])
        auth=self.auth(action,policy); sent=[]
        registry=ExternalStateVerifierRegistry({'http.state': lambda b,a:(True,'match')})
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),generic_adapters={'orders.create':Adapter()},external_state_registry=registry)
        with self.assertRaises(ValueError): router.execute(auth,lambda a:sent.append(a) or 'bad')
        self.assertEqual(sent,[])

    def test_required_state_blocks_adapter_that_fakes_bound_method_without_atomic_scope(self):
        class FakeBoundAdapter(Adapter):
            def execute_bound_after_consume(self, authorization, external_state, side_effect):
                return side_effect(authorization["payload"]["action"])

        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders',metadata={'external_state':{'kind':'http.state','reference':'orders','digest':'b'*64}})
        policy=Policy(external_state_requirements=[{'action_type':'orders.create','target':'orders','kind':'http.state'}])
        auth=self.auth(action,policy); sent=[]
        registry=ExternalStateVerifierRegistry({'http.state': lambda b,a:(True,'match')})
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),generic_adapters={'orders.create':FakeBoundAdapter()},external_state_registry=registry)
        with self.assertRaisesRegex(ValueError, "atomic external state enforcement"):
            router.execute(auth,lambda a:sent.append(a) or 'bad')
        self.assertEqual(sent,[])

    def test_execution_receipt_cannot_bypass_atomic_state_requirement(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders',metadata={'external_state':{'kind':'http.state','reference':'orders','digest':'b'*64}})
        policy=Policy(external_state_requirements=[{'action_type':'orders.create','target':'orders','kind':'http.state'}])
        auth=self.auth(action,policy); sent=[]
        registry=ExternalStateVerifierRegistry({'http.state': lambda b,a:(True,'match')})
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),load_private_key(self.private),generic_adapters={'orders.create':Adapter()},external_state_registry=registry)
        receipt=router.execute_with_receipt(auth,lambda a:sent.append(a) or 'should-not-run')
        self.assertEqual(receipt.payload['status'],'FAILED')
        self.assertIn('atomic external state enforcement is required',receipt.payload['error'])
        self.assertEqual(sent,[])

    def test_execution_receipt_uses_atomic_state_boundary(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders',metadata={'external_state':{'kind':'http.state','reference':'orders','digest':'b'*64}})
        policy=Policy(external_state_requirements=[{'action_type':'orders.create','target':'orders','kind':'http.state'}])
        auth=self.auth(action,policy); sent=[]
        registry=ExternalStateVerifierRegistry({'http.state': lambda b,a:(True,'match')})
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),load_private_key(self.private),generic_adapters={'orders.create':BoundAdapter()},external_state_registry=registry)
        receipt=router.execute_with_receipt(auth,lambda a:sent.append(a) or 'atomic-ok')
        self.assertEqual(receipt.payload['status'],'SUBMITTED')
        self.assertEqual(receipt.payload['transaction_ref'],'atomic-ok')
        self.assertEqual(len(sent),1)

    def test_required_verifier_missing_blocks(self):
        action=ActionIntent(agent_id='a',action_type='orders.create',target='orders',metadata={'external_state':{'kind':'http.state','reference':'orders','digest':'b'*64}})
        policy=Policy(external_state_requirements=[{'action_type':'orders.create','target':'orders','kind':'http.state'}])
        auth=self.auth(action,policy)
        router=ExecutionRouter(NetworkRegistry(),self.storage,load_public_key(self.public),generic_adapters={'orders.create':Adapter()},external_state_registry=ExternalStateVerifierRegistry())
        with self.assertRaises(ValueError): router.execute(auth,lambda a:'side-effect')

    def test_proof_external_state_accepts_atomic_contract(self):
        state={'kind':'http.state','reference':'orders','digest':'b'*64}
        requirement={'action_type':'orders.create','target':'orders','kind':'http.state'}
        import hashlib, json
        payload={
            'external_state_required':True,
            'external_state':state,
            'external_state_requirement':requirement,
            'external_state_sha256':hashlib.sha256(json.dumps(state,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
            'external_state_requirement_sha256':hashlib.sha256(json.dumps(requirement,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
        }
        ok, reason=validate_external_state_execution_scope(payload, {'execution_external_state_scope':'atomic'})
        self.assertTrue(ok, reason)

    def test_proof_external_state_rejects_missing_atomic_contract(self):
        state={'kind':'http.state','reference':'orders','digest':'b'*64}
        requirement={'action_type':'orders.create','target':'orders','kind':'http.state'}
        import hashlib, json
        payload={
            'external_state_required':True,
            'external_state':state,
            'external_state_requirement':requirement,
            'external_state_sha256':hashlib.sha256(json.dumps(state,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
            'external_state_requirement_sha256':hashlib.sha256(json.dumps(requirement,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
        }
        ok, reason=validate_external_state_execution_scope(payload, {})
        self.assertFalse(ok)
        self.assertIn('atomically enforced', reason)

    def test_proof_external_state_rejects_kind_mismatch(self):
        state={'kind':'mcp.state','reference':'orders','digest':'b'*64}
        requirement={'action_type':'orders.create','target':'orders','kind':'http.state'}
        import hashlib, json
        payload={
            'external_state_required':True,
            'external_state':state,
            'external_state_requirement':requirement,
            'external_state_sha256':hashlib.sha256(json.dumps(state,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
            'external_state_requirement_sha256':hashlib.sha256(json.dumps(requirement,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
        }
        ok, reason=validate_external_state_execution_scope(payload, {'execution_external_state_scope':'atomic'})
        self.assertFalse(ok)
        self.assertIn('kind does not satisfy', reason)

if __name__=='__main__': unittest.main()
