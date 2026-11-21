#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,hashlib,json,math,re
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
PROTOCOL='verigate-authority-proof-v1'; PKG='verigate-proof-package-v1'; MEDIA='application/vnd.verigate.proof-package+json'; ZERO='0'*64
REQUIRED_AUTHORITY_TYPES=('action_intent','execution_authorization','execution_receipt','outcome_claim','observed_effect','outcome_attestation','authority_event','authority_state','authority_state_after','authority_ledger','genesis_authority','capability')
def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(x): return hashlib.sha256(canon(x)).hexdigest()
def b64(x): return base64.b64decode(x,validate=True)
def ref(n): return f"{n['type']}:{n['id']}"
def node(p,k):
 x=[n for n in p.get('nodes',[]) if n.get('type')==k]; return x[0] if len(x)==1 else None
def edge(p,a,r,b): return any(e.get('from')==a and e.get('relation')==r and e.get('to')==b for e in p.get('edges',[]))
def merkle(xs):
 if not xs:return hashlib.sha256(b'VERIGATE-EVIDENCE-MERKLE:v1:empty').hexdigest()
 xs=sorted(xs)
 while len(xs)>1:
  if len(xs)%2:xs.append(xs[-1])
  xs=[hashlib.sha256(('pair:'+xs[i]+':'+xs[i+1]).encode()).hexdigest() for i in range(0,len(xs),2)]
 return xs[0]
def root(p):
 xs=[hashlib.sha256(('node:'+sha(n['data'])).encode()).hexdigest() for n in p.get('nodes',[])]
 xs += [hashlib.sha256(('edge:'+sha(e)).encode()).hexdigest() for e in p.get('edges',[])]
 return merkle(xs)
def bad(r,c): return {'valid':False,'protocol':PROTOCOL,'reason':r,'checks':c}
def assertions(m):
 p=m['payload']; kinds=['identity','capability','action_intent','authority_state','genesis_authority','decision','execution_authorization','execution_receipt','outcome_claim','observed_effect','outcome_attestation','authority_event','authority_state_after','authority_ledger']; n={k:node(p,k) for k in kinds}
 if any(v is None for v in n.values()): return False,'authority protocol evidence incomplete'
 R={k:ref(v) for k,v in n.items()}; ap=n['execution_authorization']['data']['payload']; rp=n['execution_receipt']['data']['payload']; cp=n['outcome_claim']['data']; oe=n['observed_effect']['data']; ep=n['authority_event']['data']; sp=n['authority_state_after']['data']; ent=n['authority_ledger']['data'].get('entries',[])
 def A(i,k,s,pr,o,e):
  x={'id':i,'kind':k,'subject':s,'predicate':pr,'object':o,'evidence':e}; x['sha256']=hashlib.sha256(canon(x)).hexdigest(); return x
 exp=[A('A1','identity',R['identity'],'possessed_capability',R['capability'],[R['identity'],R['capability']]),A('A2','intent',R['action_intent'],'proposed_by',n['identity']['data'].get('agent_id',p.get('agent_id')),[R['action_intent'],R['identity']]),A('A3','authority',R['authority_state'],'permitted',R['action_intent'],[R['authority_state'],R['action_intent'],R['capability']]),A('A4','authorization',R['execution_authorization'],'derived_from',R['authority_state'],[R['decision'],R['execution_authorization'],R['authority_state'],R['genesis_authority']]),A('A5','execution',R['execution_receipt'],'consumed_authorization',R['execution_authorization'],[R['execution_authorization'],R['execution_receipt']]),A('A6','observation',R['outcome_claim'],'observes',R['execution_receipt'],[R['execution_receipt'],R['outcome_claim'],R['observed_effect'],R['outcome_attestation']]),A('A7','learning',R['authority_event'],'justified_by',R['outcome_claim'],[R['outcome_claim'],R['authority_event']]),A('A8','learning',R['authority_state_after'],'produced_by',R['authority_event'],[R['authority_event'],R['authority_state_after']]),A('A9','integrity',R['authority_state_after'],'ledger_bound',R['authority_ledger'],[R['authority_state_after'],R['authority_ledger']])]
 astate=n['authority_state']['data']; capdata=n['capability']['data']; gd=n['genesis_authority']['data']
 authority_digest=sha({'authority_id':f"{ap.get('agent_id')}:{n['capability']['id']}:{astate.get('ledger_head_hash') or sha(astate)}",'agent_id':ap.get('agent_id'),'identity_id':ap.get('identity_id',''),'capability_id':n['capability']['id'],'capability_version':capdata.get('version',1),'capability_sha256':ap.get('capability_sha256',''),'state':astate.get('state'),'multiplier':float(astate.get('multiplier')),'epoch':astate.get('epoch',0),'ledger_head_hash':astate.get('ledger_head_hash',''),'effective_from':float(astate.get('evaluated_at',0.0)),'expires_at':None,'parent_authority_id':None,'evidence_refs':(),'metadata':{'source':'core.authority_state.AuthoritySnapshot','successes':astate.get('successes',0),'adverse_events':astate.get('adverse_events',0),'critical_events':astate.get('critical_events',0),'reason':astate.get('reason','')}})
 checks=[edge(p,R['identity'],'AUTHENTICATES',R['action_intent']),edge(p,R['capability'],'AUTHORIZES',R['action_intent']),ap.get('authority_state_sha256')==sha(n['authority_state']['data']),gd.get('authority_digest')==authority_digest,edge(p,R['decision'],'MINTS',R['execution_authorization']),edge(p,R['execution_authorization'],'PRODUCES',R['execution_receipt']),rp.get('authorization_id')==ap.get('authorization_id'),edge(p,R['execution_receipt'],'OBSERVED_BY',R['outcome_claim']),edge(p,R['outcome_claim'],'SUPPORTED_BY',R['observed_effect']),oe.get('authorization_id')==ap.get('authorization_id'),oe.get('action_sha256')==cp.get('action_sha256'),oe.get('evidence_ref')==cp.get('evidence_ref'),oe.get('result_sha256')==cp.get('result_sha256'),cp.get('observed_effect_sha256')==sha(oe),oe.get('observation_sha256')==sha({'verifier_type':oe.get('verifier_type'),'evidence_kind':oe.get('evidence_kind'),'effect_status':oe.get('effect_status'),'authorization_id':oe.get('authorization_id'),'action_sha256':oe.get('action_sha256'),'observed_at':oe.get('observed_at'),'evidence_ref':oe.get('evidence_ref'),'result_sha256':oe.get('result_sha256'),'observation':oe.get('observation')}),edge(p,R['outcome_attestation'],'ATTESTS',R['outcome_claim']),edge(p,R['outcome_claim'],'INFORMS',R['authority_event']),edge(p,R['authority_event'],'TRANSITIONS_TO',R['authority_state_after']),ep.get('evidence_ref')==cp.get('claim_id'),sp.get('source_event_id')==ep.get('event_id'),len([x for x in ent if x.get('event_id')==ep.get('event_id')])==1 and sp.get('ledger_head_hash')==next((x.get('event_hash') for x in ent if x.get('event_id')==ep.get('event_id')),None)]
 return (exp==p.get('authority_assertions') and all(checks) and sha(exp)==p.get('authority_assertions_sha256'),'signed authority assertions do not match evidence' if exp!=p.get('authority_assertions') else 'authority protocol preconditions failed')
def load_trusted_key(path):
 raw=Path(path).read_bytes()
 public_key=serialization.load_pem_public_key(raw)
 if not isinstance(public_key,Ed25519PublicKey): raise ValueError('issuer public key must be Ed25519')
 return base64.b64encode(public_key.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()

def verify_historical(snapshot,entries,policy,expected_head):
 try:
  eval_at=float(snapshot['evaluated_at']); hist=float(snapshot['history_start_at']); win=float(policy['window_seconds']); p=int(policy['probation_successes']); s=int(policy['standard_successes']); l=int(policy['limited_adverse_events']); c=int(policy['suspension_critical_events']); mult={'PROBATION':float(policy['probation_multiplier']),'LIMITED':float(policy['limited_multiplier']),'STANDARD':float(policy['standard_multiplier']),'ELEVATED':float(policy['elevated_multiplier']),'SUSPENDED':0.0}
 except Exception:return False,'historical authority policy or snapshot is malformed'
 if hist!=eval_at-win:return False,'historical authority history boundary is not policy-derived'
 if snapshot.get('authority_policy_sha256')!=sha(policy):return False,'historical authority policy binding mismatch'
 committed=[]
 if expected_head!='0'*64:
  for x in entries:
   committed.append(x)
   if x.get('event_hash')==expected_head:break
  if not committed or committed[-1].get('event_hash')!=expected_head:return False,'historical authority ledger head is not present'
 for x in entries[len(committed):]:
  e=x.get('event') if isinstance(x,dict) else None
  if not isinstance(e,dict):return False,'historical authority future event is malformed'
  t=e.get('occurred_at')
  if not isinstance(t,(int,float)) or isinstance(t,bool):return False,'historical authority future event timestamp is invalid'
  if float(t)<=eval_at:return False,'historical authority head is inconsistent with evaluation time'
 succ=adv=crit=0; advset={'EXECUTION_FAILED','AUTHORIZATION_REJECTED','POLICY_VIOLATION','TAMPER_DETECTED'}; critset={'TAMPER_DETECTED','POLICY_VIOLATION'}
 for row in committed:
  e=row.get('event') if isinstance(row,dict) else None
  if not isinstance(e,dict):return False,'historical authority ledger contains malformed event'
  t=e.get('occurred_at')
  if not isinstance(t,(int,float)) or isinstance(t,bool):return False,'historical authority event timestamp is invalid'
  if hist<=float(t)<=eval_at:
   succ+=1 if e.get('event_type')=='EXECUTION_CONFIRMED' else 0; adv+=1 if e.get('event_type') in advset else 0; crit+=1 if e.get('event_type') in critset else 0
 if (snapshot.get('successes'),snapshot.get('adverse_events'),snapshot.get('critical_events'))!=(succ,adv,crit):return False,'historical authority counters do not match ledger history'
 if crit>=c:state='SUSPENDED';reason='critical authority event observed'
 elif adv>=l:state='LIMITED';reason='adverse outcome threshold reached'
 elif succ>=s and adv<=1:state='ELEVATED';reason='verified success threshold reached with bounded adverse history'
 elif succ>=p and adv<=1:state='STANDARD';reason='probation success threshold reached'
 else:state='PROBATION';reason='insufficient verified history for broader authority'
 if snapshot.get('state')!=state:return False,'historical authority state is not deterministically justified'
 if snapshot.get('multiplier')!=mult[state]:return False,'historical authority multiplier is inconsistent'
 if snapshot.get('reason')!=reason:return False,'historical authority reason is inconsistent'
 return True,'valid historical authority'

def verify_learning(claim,att,ev,before,after,entries,policy,expected_head):
 if claim.get('status')=='SUCCEEDED': et='EXECUTION_CONFIRMED'
 elif claim.get('status')=='FAILED': et='EXECUTION_FAILED'
 else: return False,'authority lifecycle learning requires a terminal independent outcome'
 agent=claim.get('agent_id'); cap=before.get('capability_id'); cid=claim.get('claim_id')
 if ev.get('agent_id')!=agent or ev.get('capability_id')!=cap or ev.get('event_type')!=et or ev.get('evidence_ref')!=cid:return False,'authority event does not match canonical outcome'
 if ev.get('event_id')!=hashlib.sha256(f"{agent}:{cap}:{et}:{cid}".encode()).hexdigest():return False,'authority event id is not deterministic'
 meta=ev.get('metadata') if isinstance(ev.get('metadata'),dict) else {}
 if 'outcome_attestation_id' in meta and meta.get('outcome_attestation_id')!=att.get('attestation_id'):return False,'authority event is not bound to outcome attestation'
 if 'attestation_type' in meta and meta.get('attestation_type')!=att.get('attestor_type'):return False,'authority event attestation type is inconsistent'
 try:
  eval_at=float(after['evaluated_at']); hist=float(after['history_start_at']); win=float(policy['window_seconds'])
  thresholds=(int(policy['probation_successes']),int(policy['standard_successes']),int(policy['limited_adverse_events']),int(policy['suspension_critical_events']))
  mult={'PROBATION':float(policy['probation_multiplier']),'LIMITED':float(policy['limited_multiplier']),'STANDARD':float(policy['standard_multiplier']),'ELEVATED':float(policy['elevated_multiplier']),'SUSPENDED':0.0}
 except Exception:return False,'authority policy or post-learning snapshot is malformed'
 if hist!=eval_at-win:return False,'post-learning authority history boundary is not policy-derived'
 if after.get('authority_policy_sha256')!=sha(policy):return False,'post-learning authority policy binding mismatch'
 if after.get('agent_id')!=agent or after.get('capability_id')!=cap:return False,'post-learning authority snapshot identity mismatch'
 eh=sha(ev); matches=[x for x in entries if isinstance(x,dict) and x.get('event_id')==ev.get('event_id')]
 if len(matches)!=1 or matches[0].get('event_hash')!=eh or matches[0].get('event')!=ev:return False,'authority ledger event is not exact canonical learning evidence'
 if after.get('ledger_head_hash')!=eh:return False,'post-learning authority is not bound to the learning event hash'
 try: event_at=float(ev['occurred_at']); before_at=float(before['evaluated_at'])
 except Exception:return False,'authority learning timestamps are malformed'
 if event_at>eval_at or event_at<hist:return False,'learning event is outside the post-learning authority evaluation window'
 if before_at>eval_at:return False,'post-learning authority is evaluated before the historical snapshot'
 if before.get('ledger_head_hash')!=expected_head:return False,'historical authority snapshot is not bound to authorization head'
 prior=next((x.get('sequence') for x in entries if x.get('event_hash')==expected_head),0)
 seq=matches[0].get('sequence')
 if expected_head!='0'*64 and prior==0:return False,'authorization ledger head is not present in authority ledger'
 if not isinstance(seq,int) or seq<=prior:return False,'learning event does not extend authorization ledger head'
 for x in entries:
  if isinstance(x,dict) and isinstance(x.get('sequence'),int) and x['sequence']>seq:
   fe=x.get('event')
   if isinstance(fe,dict) and float(fe.get('occurred_at',eval_at+1))<=eval_at:return False,'post-learning snapshot is not bound to ledger head at evaluation time'
 successes=adverse=critical=0; adv={'EXECUTION_FAILED','AUTHORIZATION_REJECTED','POLICY_VIOLATION','TAMPER_DETECTED'}; crit={'TAMPER_DETECTED','POLICY_VIOLATION'}
 for row in entries:
  e=row.get('event') if isinstance(row,dict) else None
  if not isinstance(e,dict):return False,'authority ledger contains malformed event'
  t=e.get('occurred_at')
  if not isinstance(t,(int,float)) or isinstance(t,bool):return False,'authority event timestamp is invalid'
  if hist<=float(t)<=eval_at:
   successes+=1 if e.get('event_type')=='EXECUTION_CONFIRMED' else 0; adverse+=1 if e.get('event_type') in adv else 0; critical+=1 if e.get('event_type') in crit else 0
 if (after.get('successes'),after.get('adverse_events'),after.get('critical_events'))!=(successes,adverse,critical):return False,'post-learning authority counters do not match ledger history'
 p,s,l,c=thresholds; prev=before.get('state')
 if prev=='SUSPENDED': state='SUSPENDED'; reason='suspended until an explicit authority reset'
 elif critical>=c: state='SUSPENDED'; reason='critical authority event observed'
 elif adverse>=l: state='LIMITED'; reason='adverse outcome threshold reached'
 elif successes>=s and adverse<=1: state='ELEVATED'; reason='verified success threshold reached with bounded adverse history'
 elif successes>=p and adverse<=1: state='STANDARD'; reason='probation success threshold reached'
 else: state='PROBATION'; reason='insufficient verified history for broader authority'
 if after.get('state')!=state:return False,'post-learning authority state is not deterministically justified'
 if after.get('multiplier')!=mult[state]:return False,'post-learning authority multiplier is inconsistent'
 if after.get('reason')!=reason:return False,'post-learning authority reason is inconsistent'
 return True,'valid deterministic learning transition'


def verify_governance(p, attestor_id, attestor_data):
    """Independently verify the governance quorum behind an attestor."""
    nodes = {ref(item): item for item in p.get("nodes", [])}
    actions = [
        item for item in p.get("nodes", [])
        if item.get("type") == "governance_action"
        and isinstance(item.get("data"), dict)
        and item["data"].get("attestor_id") == attestor_id
        and edge(
            p,
            f"attestor_authority:{attestor_id}",
            "DERIVED_FROM",
            ref(item),
        )
    ]
    if not actions:
        return False, "attestor governance lineage is missing", None

    verified_actions = []
    for action_node in actions:
        action = action_node["data"]
        action_id = action_node.get("id")
        action_ref = f"governance_action:{action_id}"
        if action.get("action_id") != action_id:
            return False, "governance action ID does not match its evidence node", None

        policy_edges = [
            item for item in p.get("edges", [])
            if item.get("relation") == "GOVERNS"
            and item.get("to") == action_ref
        ]
        if len(policy_edges) != 1:
            return False, "governance action must have exactly one policy", None
        policy_node = nodes.get(policy_edges[0].get("from"))
        if policy_node is None or policy_node.get("type") != "governance_policy":
            return False, "governance policy evidence is missing", None
        raw_policy = policy_node.get("data")
        if not isinstance(raw_policy, dict) or raw_policy.get("governance_version") != 1:
            return False, "governance policy evidence is malformed", None

        try:
            members = raw_policy["members"]
            required_roles = raw_policy.get("required_roles", {})
            allowed_actions = raw_policy.get("allowed_actions", ["AUTHORITY_RESET"])
            policy = {
                "governance_version": 1,
                "policy_id": raw_policy["policy_id"],
                "version": int(raw_policy.get("version", 1)),
                "threshold": int(raw_policy["threshold"]),
                "members": [],
                "required_roles": {
                    str(role): int(count) for role, count in required_roles.items()
                },
                "max_approval_lifetime_seconds": int(
                    raw_policy.get("max_approval_lifetime_seconds", 300)
                ),
                "allowed_actions": list(allowed_actions),
            }
            if not isinstance(members, list) or not isinstance(required_roles, dict):
                return False, "governance policy members or role requirements are malformed", None
            if not isinstance(allowed_actions, (list, tuple)):
                return False, "governance policy allowed actions are malformed", None
            member_map = {}
            member_keys = set()
            for member in members:
                if not isinstance(member, dict):
                    return False, "governance policy member is malformed", None
                governor = member.get("governor_id")
                role = member.get("role")
                public_key_b64 = member.get("public_key_b64")
                raw_key = b64(public_key_b64)
                if len(raw_key) != 32 or hashlib.sha256(raw_key).hexdigest() != governor:
                    return False, "governance member public-key fingerprint mismatch", None
                if not isinstance(role, str) or not role or governor in member_map or raw_key in member_keys:
                    return False, "governance policy has duplicate or invalid members", None
                policy["members"].append({
                    "governor_id": governor,
                    "role": role,
                    "public_key_b64": public_key_b64,
                })
                member_map[governor] = (role, Ed25519PublicKey.from_public_bytes(raw_key))
                member_keys.add(raw_key)
            threshold = policy["threshold"]
            lifetime = policy["max_approval_lifetime_seconds"]
            if (
                threshold < 1
                or threshold > len(member_map)
                or lifetime <= 0
                or policy["version"] < 1
                or not policy["policy_id"]
                or not policy["allowed_actions"]
                or any(not isinstance(item, str) or not item for item in policy["allowed_actions"])
            ):
                return False, "governance policy thresholds or metadata are invalid", None
            if any(not role or count < 1 for role, count in policy["required_roles"].items()):
                return False, "governance policy required roles are invalid", None
            if any(
                count > sum(1 for role, _key in member_map.values() if role == required_role)
                for required_role, count in policy["required_roles"].items()
            ):
                return False, "governance policy requires unavailable roles", None
            if sha(policy) != action.get("governance_policy_sha256"):
                return False, "governance action policy fingerprint mismatch", None
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
            return False, "governance policy evidence is malformed", None

        if action.get("attestor_id") != attestor_id or action.get("action") not in policy["allowed_actions"]:
            return False, "governance action is not allowed for this attestor", None
        if action.get("governance_version") != 1:
            return False, "unsupported governance action version", None
        for field in ("action_id", "reason", "nonce"):
            if not isinstance(action.get(field), str) or not action[field]:
                return False, "governance action fields are invalid", None
        action_issued = action.get("issued_at")
        action_expires = action.get("expires_at")
        if (
            isinstance(action_issued, bool)
            or not isinstance(action_issued, (int, float))
            or isinstance(action_expires, bool)
            or not isinstance(action_expires, (int, float))
            or not math.isfinite(float(action_issued))
            or not math.isfinite(float(action_expires))
            or action_expires <= action_issued
            or action_expires - action_issued > lifetime
        ):
            return False, "governance action timestamps are invalid", None

        approval_edges = [
            item for item in p.get("edges", [])
            if item.get("relation") == "APPROVES"
            and item.get("to") == action_ref
        ]
        if not approval_edges:
            return False, "governance action has no approvals", None

        approvals = []
        issue_times = [float(action_issued)]
        seen_governors = set()
        seen_nonces = set()
        role_counts = {}
        for item in approval_edges:
            approval_node = nodes.get(item.get("from"))
            if approval_node is None or approval_node.get("type") != "governance_approval":
                return False, "governance approval evidence is missing", None
            signed = approval_node.get("data")
            approval = signed.get("payload") if isinstance(signed, dict) else None
            if not isinstance(approval, dict) or approval.get("approval_id") != approval_node.get("id"):
                return False, "governance approval identity is inconsistent", None
            if signed.get("algorithm") != "Ed25519" or approval.get("governance_version") != 1:
                return False, "unsupported governance approval format", None
            if approval.get("action_digest") != sha(action):
                return False, "governance approval targets a different action", None
            governor = approval.get("governor_id")
            member = member_map.get(governor)
            if member is None or member[0] != approval.get("role"):
                return False, "governance signer is not authorized for this role", None
            if governor in seen_governors:
                return False, "duplicate governance signer", None
            nonce = approval.get("nonce")
            if not isinstance(nonce, str) or not nonce or nonce in seen_nonces:
                return False, "duplicate or invalid governance approval nonce", None
            issued = approval.get("issued_at")
            expires = approval.get("expires_at")
            if (
                isinstance(issued, bool)
                or not isinstance(issued, (int, float))
                or isinstance(expires, bool)
                or not isinstance(expires, (int, float))
                or not math.isfinite(float(issued))
                or not math.isfinite(float(expires))
                or expires <= issued
                or expires - issued > lifetime
            ):
                return False, "governance approval timestamps are invalid", None
            try:
                member[1].verify(b64(signed.get("signature")), canon(approval))
            except (InvalidSignature, ValueError, TypeError):
                return False, "governance approval signature is invalid", None
            issue_times.append(float(issued))
            seen_governors.add(governor)
            seen_nonces.add(nonce)
            role_counts[approval["role"]] = role_counts.get(approval["role"], 0) + 1
            approvals.append(signed)

        # The quorum is checked at the first instant all collected signatures
        # existed, rather than today's clock. Historical proofs therefore remain
        # verifiable after the short-lived approvals have naturally expired.
        verification_time = max(issue_times)
        if action_expires <= verification_time:
            return False, "governance action expired before the complete quorum existed", None
        if len(approvals) < threshold:
            return False, "governance approval threshold was not reached", None
        for role, count in policy["required_roles"].items():
            if role_counts.get(role, 0) < count:
                return False, f"governance required role missing: {role}", None
        if any(
            signed["payload"]["expires_at"] <= verification_time
            or signed["payload"]["issued_at"] > verification_time + 60
            for signed in approvals
        ):
            return False, "governance approval was not valid when the complete quorum existed", None
        if action_issued > verification_time + 60:
            return False, "governance action issue time is invalid", None
        verified_actions.append((verification_time, action))

    attestation_node = node(p, "outcome_attestation")
    attestation_payload = attestation_node.get("data", {}).get("payload", {}) if attestation_node else {}
    attested_at = attestation_payload.get("attested_at")
    if (
        isinstance(attested_at, bool)
        or not isinstance(attested_at, (int, float))
        or not math.isfinite(float(attested_at))
    ):
        return False, "outcome attestation timestamp is invalid", None

    ordered_actions = sorted(verified_actions, key=lambda item: item[0])
    previous_time = None
    registered = False
    state = "UNREGISTERED"
    public_key_b64 = None
    key_id = None
    attestor_type = None
    expires_at = None
    revoked_at = None
    state_at_attestation = None

    for effective_at, action in ordered_actions:
        if previous_time is not None and effective_at <= previous_time:
            return False, "attestor governance actions have ambiguous or non-monotonic ordering", None
        previous_time = effective_at
        operation = action.get("action")

        if operation == "ATTESTOR_REGISTER":
            if registered:
                return False, "attestor governance history contains a duplicate registration", None
            next_key_b64 = action.get("public_key_b64")
            next_type = action.get("attestor_type")
            try:
                raw_key = b64(next_key_b64)
                if len(raw_key) != 32:
                    raise ValueError("Ed25519 key must be 32 bytes")
                if next_type not in ("EXECUTOR", "EXTERNAL_VERIFIER", "CHAIN_VERIFIER"):
                    raise ValueError("invalid attestor type")
                next_expiry = action.get("attestor_expires_at")
                if next_expiry is not None and (
                    isinstance(next_expiry, bool)
                    or not isinstance(next_expiry, (int, float))
                    or not math.isfinite(float(next_expiry))
                ):
                    raise ValueError("invalid attestor expiry")
            except (TypeError, ValueError):
                return False, "attestor registration contains an invalid key, type or expiry", None
            registered = True
            state = "ACTIVE"
            public_key_b64 = next_key_b64
            key_id = hashlib.sha256(raw_key).hexdigest()
            attestor_type = next_type
            expires_at = next_expiry
            revoked_at = None

        elif operation == "ATTESTOR_ACTIVATE":
            if not registered:
                return False, "attestor activation precedes registration", None
            state = "ACTIVE"

        elif operation == "ATTESTOR_ROTATE":
            if not registered:
                return False, "attestor rotation precedes registration", None
            next_key_b64 = action.get("public_key_b64")
            next_type = action.get("attestor_type")
            try:
                raw_key = b64(next_key_b64)
                if len(raw_key) != 32:
                    raise ValueError("Ed25519 key must be 32 bytes")
                if next_type not in ("EXECUTOR", "EXTERNAL_VERIFIER", "CHAIN_VERIFIER"):
                    raise ValueError("invalid attestor type")
                next_expiry = action.get("attestor_expires_at")
                if next_expiry is not None and (
                    isinstance(next_expiry, bool)
                    or not isinstance(next_expiry, (int, float))
                    or not math.isfinite(float(next_expiry))
                ):
                    raise ValueError("invalid attestor expiry")
            except (TypeError, ValueError):
                return False, "attestor rotation contains an invalid key, type or expiry", None
            state = "ACTIVE"
            public_key_b64 = next_key_b64
            key_id = hashlib.sha256(raw_key).hexdigest()
            attestor_type = next_type
            expires_at = next_expiry
            revoked_at = None

        elif operation == "ATTESTOR_REVOKE":
            if not registered or state != "ACTIVE":
                return False, "attestor revocation does not follow an active registration", None
            state = "REVOKED"
            revoked_at = effective_at

        elif operation == "ATTESTOR_EXPIRE":
            if not registered:
                return False, "attestor expiry precedes registration", None
            state = "EXPIRED"

        else:
            return False, "unsupported attestor governance state transition", None

        if effective_at <= float(attested_at):
            state_at_attestation = {
                "status": state,
                "public_key_b64": public_key_b64,
                "key_id": key_id,
                "attestor_type": attestor_type,
                "expires_at": expires_at,
                "revoked_at": revoked_at,
            }

    if not registered:
        return False, "attestor governance history has no registration", None

    if (
        attestor_data.get("status") != state
        or attestor_data.get("public_key_b64") != public_key_b64
        or attestor_data.get("key_id") != key_id
        or attestor_data.get("attestor_type") != attestor_type
        or attestor_data.get("expires_at") != expires_at
        or bool(attestor_data.get("revoked_at")) != bool(revoked_at)
    ):
        return False, "attestor registry snapshot does not match replayed governance state", None

    if state_at_attestation is None:
        return False, "attestor was not registered when the outcome was attested", None
    if state_at_attestation["status"] != "ACTIVE":
        return False, "attestor was not active when the outcome was attested", None

    historical_attestor = dict(attestor_data)
    historical_attestor.update(state_at_attestation)
    if historical_attestor.get("status") == "ACTIVE":
        # A retained revoked_at timestamp is historical audit data after reactivation.
        historical_attestor["revoked_at"] = None
    return True, "governance policy, signatures, quorum and historical attestor state verified", historical_attestor


def verify_outcome_attestation(attestation, attestor):
    """Verify the independent attestor signature and authority at attestation time."""
    if not isinstance(attestation, dict) or attestation.get("algorithm") != "Ed25519":
        return False, "unsupported outcome attestation signature algorithm"
    payload = attestation.get("payload")
    if not isinstance(payload, dict):
        return False, "outcome attestation payload is malformed"
    if payload.get("attestor_id") != attestor.get("attestor_id"):
        return False, "outcome attestation signer identity mismatch"

    registered_type = attestor.get("attestor_type")
    expected_type = "EXECUTOR_SELF_REPORT" if registered_type == "EXECUTOR" else registered_type
    if expected_type not in ("EXECUTOR_SELF_REPORT", "EXTERNAL_VERIFIER", "CHAIN_VERIFIER"):
        return False, "registered outcome attestor type is invalid"
    if payload.get("attestor_type") != expected_type:
        return False, "outcome attestation type does not match registered attestor"

    attested_at = payload.get("attested_at")
    created_at = attestor.get("created_at")
    if (
        isinstance(attested_at, bool)
        or not isinstance(attested_at, (int, float))
        or not math.isfinite(float(attested_at))
        or isinstance(created_at, bool)
        or not isinstance(created_at, (int, float))
        or not math.isfinite(float(created_at))
        or float(attested_at) < float(created_at)
    ):
        return False, "outcome attestation time is invalid for registered attestor authority"

    for field, label in (("expires_at", "expiry"), ("revoked_at", "revocation")):
        boundary = attestor.get(field)
        if boundary is not None:
            if (
                isinstance(boundary, bool)
                or not isinstance(boundary, (int, float))
                or not math.isfinite(float(boundary))
            ):
                return False, f"registered attestor {label} time is invalid"
            if float(attested_at) >= float(boundary):
                return False, f"outcome attestor authority had {label} before attestation"

    try:
        raw_key = b64(attestor.get("public_key_b64"))
        if len(raw_key) != 32:
            return False, "registered attestor Ed25519 public key must be 32 bytes"
        if hashlib.sha256(raw_key).hexdigest() != attestor.get("key_id"):
            return False, "registered attestor public-key fingerprint mismatch"
        public_key = Ed25519PublicKey.from_public_bytes(raw_key)
        public_key.verify(b64(attestation.get("signature")), canon(payload))
    except (InvalidSignature, TypeError, ValueError):
        return False, "outcome attestation signature verification failed"
    return True, "outcome attestation signature and historical authority verified"

def normalize_trusted_governance_policy_digests(values):
    if values is None:
        return None
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)) or not values:
        raise ValueError("at least one trusted governance policy digest is required")
    normalized = set()
    for value in values:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in value)
        ):
            raise ValueError(
                "trusted governance policy digest must be exactly 64 hexadecimal characters"
            )
        normalized.add(value.lower())
    return normalized


def trusted_policy_digest_argument(value):
    try:
        normalized = normalize_trusted_governance_policy_digests([value])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return next(iter(normalized))


def verify_governance_policy_trust_anchor(p, attestor_id, trusted_digests):
    actions = [
        item for item in p.get("nodes", [])
        if item.get("type") == "governance_action"
        and isinstance(item.get("data"), dict)
        and item["data"].get("attestor_id") == attestor_id
        and edge(
            p,
            f"attestor_authority:{attestor_id}",
            "DERIVED_FROM",
            ref(item),
        )
    ]
    policy_digests = sorted({
        item["data"].get("governance_policy_sha256")
        for item in actions
    })
    if not actions or not policy_digests or any(not isinstance(item, str) for item in policy_digests):
        return {
            "valid": False,
            "pinned": trusted_digests is not None,
            "policy_sha256": policy_digests,
            "trusted_policy_sha256": sorted(trusted_digests or ()),
            "untrusted_policy_sha256": policy_digests,
            "reason": "governance policy digests are missing from attestor lineage",
        }
    if trusted_digests is None:
        return {
            "valid": True,
            "pinned": False,
            "policy_sha256": policy_digests,
            "trusted_policy_sha256": [],
            "untrusted_policy_sha256": [],
            "reason": (
                "no trusted governance policy digest supplied; policy integrity and "
                "quorum are verified, but the governance roster is not externally pinned"
            ),
        }
    untrusted = sorted(set(policy_digests) - trusted_digests)
    if untrusted:
        return {
            "valid": False,
            "pinned": True,
            "policy_sha256": policy_digests,
            "trusted_policy_sha256": sorted(trusted_digests),
            "untrusted_policy_sha256": untrusted,
            "reason": (
                "governance policy digest is not present in the trusted allowlist: "
                + ", ".join(untrusted)
            ),
        }
    return {
        "valid": True,
        "pinned": True,
        "policy_sha256": policy_digests,
        "trusted_policy_sha256": sorted(trusted_digests),
        "untrusted_policy_sha256": [],
        "reason": "every governance policy in the attestor lineage matches the trusted allowlist",
    }



def _finite_wallet_time(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _wallet_governance_quorum(envelope):
    if not isinstance(envelope, dict) or envelope.get("algorithm") != "Ed25519-MULTIPARTY":
        return False, "unsupported wallet governance envelope", None, None
    action = envelope.get("action")
    approvals = envelope.get("approvals")
    policy = envelope.get("governance_policy")
    if not isinstance(action, dict) or not isinstance(approvals, list) or not approvals or not isinstance(policy, dict):
        return False, "wallet governance envelope is incomplete", None, None
    if policy.get("governance_version") != 1:
        return False, "unsupported wallet governance policy version", None, None

    try:
        version = policy.get("version")
        threshold = policy.get("threshold")
        lifetime = policy.get("max_approval_lifetime_seconds")
        members = policy.get("members")
        required_roles = policy.get("required_roles", {})
        allowed_actions = policy.get("allowed_actions", [])
        if (
            isinstance(version, bool) or not isinstance(version, int) or version < 1
            or isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1
            or isinstance(lifetime, bool) or not isinstance(lifetime, int) or lifetime < 1
            or not isinstance(members, list) or not isinstance(required_roles, dict)
            or not isinstance(allowed_actions, list) or not allowed_actions
        ):
            return False, "wallet governance policy metadata is invalid", None, None

        member_map = {}
        public_keys = set()
        for item in members:
            if not isinstance(item, dict):
                return False, "wallet governance policy member is malformed", None, None
            governor = item.get("governor_id")
            role = item.get("role")
            raw_key = b64(item.get("public_key_b64"))
            if (
                not isinstance(governor, str) or len(raw_key) != 32
                or hashlib.sha256(raw_key).hexdigest() != governor
                or not isinstance(role, str) or not role
                or governor in member_map or raw_key in public_keys
            ):
                return False, "wallet governance policy member identity is invalid", None, None
            member_map[governor] = (role, Ed25519PublicKey.from_public_bytes(raw_key))
            public_keys.add(raw_key)
        if threshold > len(member_map):
            return False, "wallet governance threshold exceeds member count", None, None
        if any(not isinstance(item, str) or not item for item in allowed_actions):
            return False, "wallet governance allowed actions are invalid", None, None
        for role, count in required_roles.items():
            if (
                not isinstance(role, str) or not role
                or isinstance(count, bool) or not isinstance(count, int) or count < 1
                or count > sum(1 for member_role, _ in member_map.values() if member_role == role)
            ):
                return False, "wallet governance required role is invalid", None, None
    except (KeyError, TypeError, ValueError, OverflowError):
        return False, "wallet governance policy evidence is malformed", None, None

    policy_digest = sha(policy)
    if (
        policy_digest != action.get("governance_policy_sha256")
        or envelope.get("governance_policy_sha256") != policy_digest
        or envelope.get("action_sha256") != sha(action)
    ):
        return False, "wallet governance policy or action fingerprint mismatch", None, None

    operation = action.get("action")
    if operation not in ("WALLET_ENROLL", "WALLET_REVOKE") or operation not in allowed_actions:
        return False, "wallet governance action is not allowed by its policy", None, None
    for field in ("action_id", "reason", "nonce", "enrollment_id"):
        if not isinstance(action.get(field), str) or not action[field]:
            return False, "wallet governance action fields are invalid", None, None
    action_issued = action.get("issued_at")
    action_expires = action.get("expires_at")
    if (
        not _finite_wallet_time(action_issued)
        or not _finite_wallet_time(action_expires)
        or action_expires <= action_issued
        or action_expires - action_issued > lifetime
    ):
        return False, "wallet governance action timestamps are invalid", None, None

    seen_approvals = set()
    seen_governors = set()
    seen_nonces = set()
    role_counts = {}
    approval_issued = []
    action_digest = sha(action)
    for signed in approvals:
        payload = signed.get("payload") if isinstance(signed, dict) else None
        if not isinstance(payload, dict) or signed.get("algorithm") != "Ed25519":
            return False, "wallet governance approval is malformed", None, None
        approval_id = payload.get("approval_id")
        governor = payload.get("governor_id")
        nonce = payload.get("nonce")
        role = payload.get("role")
        issued = payload.get("issued_at")
        expires = payload.get("expires_at")
        if (
            payload.get("governance_version") != 1
            or not isinstance(approval_id, str) or not approval_id or approval_id in seen_approvals
            or not isinstance(governor, str) or not governor or governor in seen_governors
            or not isinstance(nonce, str) or not nonce or nonce in seen_nonces
            or payload.get("action_digest") != action_digest
            or not _finite_wallet_time(issued)
            or not _finite_wallet_time(expires)
            or expires <= issued
            or expires - issued > lifetime
        ):
            return False, "wallet governance approval identity, binding or timestamps are invalid", None, None
        member = member_map.get(governor)
        if member is None or member[0] != role:
            return False, "wallet governance signer is not authorized for this role", None, None
        try:
            member[1].verify(b64(signed.get("signature")), canon(payload))
        except (InvalidSignature, TypeError, ValueError):
            return False, "wallet governance approval signature verification failed", None, None
        seen_approvals.add(approval_id)
        seen_governors.add(governor)
        seen_nonces.add(nonce)
        role_counts[role] = role_counts.get(role, 0) + 1
        approval_issued.append(float(issued))

    if len(seen_approvals) < threshold:
        return False, "wallet governance quorum threshold not reached", None, None
    for role, minimum in required_roles.items():
        if role_counts.get(role, 0) < minimum:
            return False, f"wallet governance required role missing: {role}", None, None

    effective_at = max([float(action_issued), *approval_issued])
    if action_expires <= effective_at:
        return False, "wallet governance action expired before its complete quorum existed", None, None
    if any(
        not _finite_wallet_time(item.get("payload", {}).get("expires_at"))
        or item["payload"]["expires_at"] <= effective_at
        for item in approvals
    ):
        return False, "wallet governance approval expired before the complete quorum existed", None, None
    return True, "wallet governance quorum verified", action, effective_at


def verify_wallet_enrollment_history(
    payload,
    *,
    installation_principal,
    chain_id,
    wallet_address,
    attested_at,
    trusted_policy_digests=None,
    trusted_history_digests=None,
):
    """Verify portable wallet enrollment snapshots and their complete governed history."""
    checks = {}
    failure = lambda reason: (False, reason, None, checks)
    if (
        not isinstance(installation_principal, str)
        or not installation_principal.startswith("anna-installation:")
        or isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id <= 0
        or not isinstance(wallet_address, str)
        or not re.fullmatch(r"0x[0-9a-fA-F]{40}", wallet_address)
        or not _finite_wallet_time(attested_at)
    ):
        return failure("wallet enrollment verification request is malformed")

    history_nodes = [
        item for item in payload.get("nodes", [])
        if item.get("type") == "wallet_enrollment_governance_history"
        and item.get("id") == installation_principal
    ]
    if len(history_nodes) != 1:
        return failure("wallet enrollment governance history evidence is missing or ambiguous")
    history_data = history_nodes[0].get("data")
    if not isinstance(history_data, dict) or history_data.get("installation_principal") != installation_principal:
        return failure("wallet enrollment governance history identity mismatch")
    envelopes = history_data.get("envelopes")
    if not isinstance(envelopes, list) or not envelopes:
        return failure("wallet enrollment governance history is empty")
    try:
        ordered_envelopes = sorted(
            envelopes,
            key=lambda item: item.get("action", {}).get("action_id", "")
            if isinstance(item, dict) else "",
        )
    except (AttributeError, TypeError):
        return failure("wallet enrollment governance history is malformed")
    history_sha256 = sha(ordered_envelopes)
    if history_data.get("history_sha256") != history_sha256:
        checks["wallet_enrollment_history_anchor"] = {
            "valid": False, "pinned": trusted_history_digests is not None,
            "history_sha256": history_data.get("history_sha256"),
            "reason": "wallet enrollment governance history fingerprint mismatch",
        }
        return failure("wallet enrollment governance history fingerprint mismatch")

    trusted_history = normalize_trusted_governance_policy_digests(trusted_history_digests)
    if trusted_history is None:
        checks["wallet_enrollment_history_anchor"] = {
            "valid": True, "pinned": False, "history_sha256": history_sha256,
            "trusted_history_sha256": [],
            "reason": "no independent wallet enrollment history digest supplied",
        }
    else:
        untrusted_history = sorted({history_sha256} - trusted_history)
        checks["wallet_enrollment_history_anchor"] = {
            "valid": not untrusted_history, "pinned": True,
            "history_sha256": history_sha256,
            "trusted_history_sha256": sorted(trusted_history),
            "untrusted_history_sha256": untrusted_history,
            "reason": "wallet enrollment history matches trusted digest" if not untrusted_history
                else "wallet enrollment history digest is not present in the trusted allowlist",
        }
        if untrusted_history:
            return failure(checks["wallet_enrollment_history_anchor"]["reason"])

    enrollment_nodes = [
        item for item in payload.get("nodes", [])
        if item.get("type") == "wallet_enrollment"
        and isinstance(item.get("data"), dict)
        and item["data"].get("installation_principal") == installation_principal
    ]
    enrollment_ids = [item.get("id") for item in enrollment_nodes]
    if not enrollment_nodes or len(set(enrollment_ids)) != len(enrollment_ids):
        return failure("wallet enrollment registry snapshots are missing or duplicated")
    if any(not isinstance(item, str) or not item for item in enrollment_ids):
        return failure("wallet enrollment registry snapshot identity is invalid")
    history_ref = f"wallet_enrollment_governance_history:{installation_principal}"
    for enrollment_node in enrollment_nodes:
        enrollment_ref = f"wallet_enrollment:{enrollment_node['id']}"
        covering_edges = [
            edge_item for edge_item in payload.get("edges", [])
            if edge_item.get("from") == history_ref
            and edge_item.get("relation") == "COVERS"
            and edge_item.get("to") == enrollment_ref
        ]
        if len(covering_edges) != 1:
            return failure("wallet enrollment snapshot is not uniquely covered by its governance history")

    verified_actions = []
    seen_action_ids = set()
    for envelope in ordered_envelopes:
        valid, reason, action, effective_at = _wallet_governance_quorum(envelope)
        if not valid:
            return failure(reason)
        action_id = action.get("action_id")
        enrollment_id = action.get("enrollment_id")
        if (
            action_id in seen_action_ids
            or enrollment_id not in enrollment_ids
        ):
            return failure("wallet enrollment governance action is duplicated or targets a missing registry row")
        seen_action_ids.add(action_id)
        verified_actions.append((effective_at, action, envelope))

    if not verified_actions:
        return failure("wallet enrollment governance history has no verified actions")
    policy_digests = sorted({
        envelope.get("governance_policy_sha256")
        for _effective_at, _action, envelope in verified_actions
    })
    if any(not isinstance(item, str) or len(item) != 64 for item in policy_digests):
        return failure("wallet governance policy digests are malformed")
    trusted_policies = normalize_trusted_governance_policy_digests(trusted_policy_digests)
    if trusted_policies is None:
        checks["wallet_governance_policy_trust_anchor"] = {
            "valid": True, "pinned": False, "policy_sha256": policy_digests,
            "trusted_policy_sha256": [],
            "reason": "wallet governance quorum is verified, but the governor roster is not externally pinned",
        }
    else:
        untrusted_policies = sorted(set(policy_digests) - trusted_policies)
        checks["wallet_governance_policy_trust_anchor"] = {
            "valid": not untrusted_policies, "pinned": True,
            "policy_sha256": policy_digests,
            "trusted_policy_sha256": sorted(trusted_policies),
            "untrusted_policy_sha256": untrusted_policies,
            "reason": "every wallet governance policy matches the trusted allowlist" if not untrusted_policies
                else "wallet governance policy digest is not present in the trusted allowlist",
        }
        if untrusted_policies:
            return failure(checks["wallet_governance_policy_trust_anchor"]["reason"])

    historical_matches = []
    for enrollment_node in enrollment_nodes:
        enrollment = enrollment_node["data"]
        enrollment_id = enrollment_node["id"]
        relevant = [
            (effective_at, action)
            for effective_at, action, _envelope in verified_actions
            if action.get("enrollment_id") == enrollment_id
        ]
        if not relevant:
            return failure("wallet enrollment registry row has no governed enrollment action")
        relevant.sort(key=lambda item: item[0])
        state = "UNREGISTERED"
        historical_state = "UNREGISTERED"
        prior_effective_at = None
        replayed_enrollment = None
        for effective_at, action in relevant:
            if prior_effective_at is not None and effective_at <= prior_effective_at:
                return failure("wallet enrollment governance actions have ambiguous or non-monotonic ordering")
            prior_effective_at = effective_at
            operation = action.get("action")
            if operation == "WALLET_ENROLL":
                if state != "UNREGISTERED":
                    return failure("wallet enrollment history contains a duplicate enrollment")
                public_key_b64 = action.get("issuer_public_key_b64")
                try:
                    raw_key = b64(public_key_b64)
                    if len(raw_key) != 32:
                        raise ValueError("invalid Ed25519 issuer key")
                    Ed25519PublicKey.from_public_bytes(raw_key)
                except (TypeError, ValueError):
                    return failure("wallet enrollment action contains an invalid issuer key")
                key_id = hashlib.sha256(raw_key).hexdigest()
                principal = "anna-installation:" + key_id
                action_chain = action.get("chain_id")
                network = action.get("network")
                wallet = action.get("wallet_address")
                confirmations = action.get("min_confirmations")
                if (
                    action.get("installation_principal") != principal
                    or action.get("issuer_key_id") != key_id
                    or not isinstance(action_chain, int) or isinstance(action_chain, bool) or action_chain <= 0
                    or not isinstance(network, str) or not network or network != network.strip().lower()
                    or not isinstance(wallet, str) or not re.fullmatch(r"0x[0-9a-f]{40}", wallet)
                    or not isinstance(confirmations, int) or isinstance(confirmations, bool) or confirmations < 1
                    or principal != installation_principal
                ):
                    return failure("wallet enrollment action bindings are invalid")
                replayed_enrollment = {
                    "enrollment_id": enrollment_id,
                    "installation_principal": principal,
                    "issuer_key_id": key_id,
                    "issuer_public_key_b64": public_key_b64,
                    "chain_id": action_chain,
                    "network": network,
                    "wallet_address": wallet,
                    "min_confirmations": confirmations,
                }
                state = "ACTIVE"
            elif operation == "WALLET_REVOKE":
                if state != "ACTIVE":
                    return failure("wallet enrollment revocation does not follow an active enrollment")
                state = "REVOKED"
            else:
                return failure("unsupported wallet enrollment governance transition")

            if effective_at <= float(attested_at):
                historical_state = state

        if replayed_enrollment is None:
            return failure("wallet enrollment history has no enrollment action")
        if any(enrollment.get(field) != value for field, value in replayed_enrollment.items()):
            return failure("wallet enrollment registry snapshot does not match governance replay")
        if enrollment.get("status") != state:
            return failure("wallet enrollment registry status does not match governance replay")
        created_at = enrollment.get("created_at")
        revoked_at = enrollment.get("revoked_at")
        if not _finite_wallet_time(created_at) or created_at <= 0:
            return failure("wallet enrollment creation timestamp is invalid")
        if state == "REVOKED":
            if not _finite_wallet_time(revoked_at) or revoked_at <= 0:
                return failure("revoked wallet enrollment timestamp is invalid")
        elif revoked_at is not None:
            return failure("active wallet enrollment has a revocation timestamp")

        if (
            enrollment.get("chain_id") == chain_id
            and enrollment.get("wallet_address") == wallet_address.lower()
            and historical_state == "ACTIVE"
        ):
            historical_enrollment = dict(enrollment)
            historical_enrollment["status"] = "ACTIVE"
            historical_enrollment["revoked_at"] = None
            historical_matches.append(historical_enrollment)

    if len(historical_matches) != 1:
        return failure("wallet was not uniquely enrolled and active when the outcome was attested")
    return True, "wallet enrollment governance state verified at attestation time", historical_matches[0], checks



def verify_wallet_governance_transparency_bundle(
    bundle,
    *,
    history_envelopes,
    installation_principal,
    trusted_log_public_key_b64=None,
    trusted_checkpoint_sha256=None,
):
    checks = {}

    def failure(reason):
        return False, reason, checks

    if (trusted_log_public_key_b64 is None) != (trusted_checkpoint_sha256 is None):
        return failure(
            "trusted wallet governance log public key and checkpoint digest must be supplied together"
        )
    if not isinstance(installation_principal, str) or not re.fullmatch(
        r"anna-installation:[0-9a-f]{64}", installation_principal
    ):
        return failure("wallet transparency log installation principal is invalid")
    if not isinstance(history_envelopes, list) or not history_envelopes:
        return failure("wallet transparency log history must be a non-empty list")
    history_by_action = {}
    for envelope in history_envelopes:
        if not isinstance(envelope, dict) or not isinstance(envelope.get("action"), dict):
            return failure("wallet transparency log envelope is malformed")
        action = envelope["action"]
        action_id = action.get("action_id")
        if (
            not isinstance(action_id, str) or not action_id
            or action_id in history_by_action
            or action.get("action") not in ("WALLET_ENROLL", "WALLET_REVOKE")
        ):
            return failure("wallet transparency log action identity is invalid or duplicated")
        if (
            action.get("action") == "WALLET_ENROLL"
            and action.get("installation_principal") != installation_principal
        ):
            return failure("wallet transparency log enrollment action has another installation principal")
        history_by_action[action_id] = envelope

    enrollment_ids = set()
    revoked_enrollment_ids = set()
    for envelope in history_envelopes:
        action = envelope["action"]
        operation = action["action"]
        enrollment_id = action.get("enrollment_id")
        if not isinstance(enrollment_id, str) or not enrollment_id:
            return failure("wallet transparency log enrollment ID is missing")
        if operation == "WALLET_ENROLL":
            if enrollment_id in enrollment_ids:
                return failure("wallet transparency log contains a duplicate enrollment ID")
            enrollment_ids.add(enrollment_id)
        else:
            if enrollment_id in revoked_enrollment_ids:
                return failure("wallet transparency log contains a duplicate wallet revocation")
            revoked_enrollment_ids.add(enrollment_id)

    unknown_revocations = sorted(revoked_enrollment_ids - enrollment_ids)
    if unknown_revocations:
        return failure(
            "wallet transparency log revocation references an enrollment outside this installation: "
            + ", ".join(unknown_revocations)
        )

    ordered_history = sorted(history_envelopes, key=lambda item: item["action"]["action_id"])
    expected_history_sha256 = sha(ordered_history)

    if (
        not isinstance(bundle, dict)
        or bundle.get("protocol") != "verigate-wallet-governance-log-v1"
        or bundle.get("installation_principal") != installation_principal
        or not isinstance(bundle.get("log_id"), str)
        or not bundle["log_id"]
        or not isinstance(bundle.get("entries"), list)
        or not bundle.get("entries")
    ):
        return failure("wallet governance transparency bundle is malformed or scoped to another principal")

    entries = bundle["entries"]
    previous_entry_sha256 = "0" * 64
    logged_actions = {}
    for sequence, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or not isinstance(entry.get("payload"), dict):
            return failure("wallet governance transparency entry is malformed")
        payload = entry["payload"]
        envelope = payload.get("envelope")
        action_id = payload.get("action_id")
        if (
            payload.get("protocol") != "verigate-wallet-governance-log-v1"
            or payload.get("log_id") != bundle["log_id"]
            or payload.get("installation_principal") != installation_principal
            or isinstance(payload.get("sequence"), bool)
            or not isinstance(payload.get("sequence"), int)
            or payload.get("sequence") != sequence
            or payload.get("previous_entry_sha256") != previous_entry_sha256
        ):
            return failure("wallet governance transparency entry sequence or hash chain mismatch")
        if (
            not isinstance(envelope, dict)
            or not isinstance(envelope.get("action"), dict)
            or not isinstance(action_id, str)
            or not action_id
            or envelope["action"].get("action_id") != action_id
        ):
            return failure("wallet governance transparency entry action identity mismatch")
        if action_id in logged_actions:
            return failure("wallet governance transparency log contains a duplicate action")
        envelope_sha256 = sha(envelope)
        if payload.get("envelope_sha256") != envelope_sha256:
            return failure("wallet governance transparency envelope digest mismatch")
        entry_sha256 = sha(payload)
        if entry.get("entry_sha256") != entry_sha256:
            return failure("wallet governance transparency entry digest mismatch")
        logged_actions[action_id] = envelope_sha256
        previous_entry_sha256 = entry_sha256

    expected_actions = {
        action_id: sha(envelope)
        for action_id, envelope in history_by_action.items()
    }
    if logged_actions != expected_actions:
        return failure(
            "wallet governance transparency entry chain does not contain the complete exact history"
        )

    checkpoint = bundle.get("checkpoint")
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("payload"), dict):
        return failure("wallet governance transparency checkpoint is missing")
    cp = checkpoint["payload"]
    checkpoint_sha256 = sha(cp)
    issued_at = cp.get("issued_at")
    if (
        checkpoint.get("algorithm") != "Ed25519"
        or checkpoint.get("checkpoint_sha256") != checkpoint_sha256
        or cp.get("protocol") != "verigate-wallet-governance-log-v1"
        or cp.get("log_id") != bundle["log_id"]
        or cp.get("installation_principal") != installation_principal
        or isinstance(cp.get("entry_count"), bool)
        or not isinstance(cp.get("entry_count"), int)
        or cp.get("entry_count") != len(entries)
        or cp.get("head_entry_sha256") != previous_entry_sha256
        or cp.get("history_sha256") != expected_history_sha256
        or isinstance(cp.get("checkpoint_sequence"), bool)
        or not isinstance(cp.get("checkpoint_sequence"), int)
        or cp["checkpoint_sequence"] < 1
        or not isinstance(cp.get("previous_checkpoint_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", cp["previous_checkpoint_sha256"])
        or (
            cp.get("checkpoint_sequence") == 1
            and cp["previous_checkpoint_sha256"] != "0" * 64
        )
        or (
            cp.get("checkpoint_sequence") > 1
            and cp["previous_checkpoint_sha256"] == "0" * 64
        )
        or not _finite_wallet_time(issued_at)
        or not isinstance(cp.get("signer_key_id"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", cp["signer_key_id"])
    ):
        return failure("wallet governance transparency checkpoint does not bind the complete log head")

    try:
        embedded_key = b64(checkpoint.get("signer_public_key_b64"))
        signature = b64(checkpoint.get("signature"))
    except (TypeError, ValueError):
        return failure("wallet governance transparency checkpoint key or signature is malformed")
    if len(embedded_key) != 32:
        return failure("wallet governance transparency checkpoint signer key must be Ed25519")
    signer_key_id = hashlib.sha256(embedded_key).hexdigest()
    if cp.get("signer_key_id") != signer_key_id:
        return failure("wallet governance transparency checkpoint signer key fingerprint mismatch")

    if trusted_log_public_key_b64 is not None:
        try:
            trusted_key = b64(trusted_log_public_key_b64)
        except (TypeError, ValueError):
            return failure("trusted wallet governance transparency public key is malformed")
        if len(trusted_key) != 32 or trusted_key != embedded_key:
            return failure("wallet governance transparency log public key does not match the trusted key")
        if (
            not isinstance(trusted_checkpoint_sha256, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", trusted_checkpoint_sha256)
            or checkpoint_sha256 != trusted_checkpoint_sha256.lower()
        ):
            checks["wallet_governance_transparency_anchor"] = {
                "valid": False,
                "pinned": True,
                "checkpoint_sha256": checkpoint_sha256,
                "trusted_checkpoint_sha256": trusted_checkpoint_sha256,
                "reason": "wallet governance transparency checkpoint does not match the trusted latest checkpoint",
            }
            return failure("wallet governance transparency checkpoint digest mismatch")
        verification_key = trusted_key
    else:
        verification_key = embedded_key

    try:
        Ed25519PublicKey.from_public_bytes(verification_key).verify(
            signature, canon(cp),
        )
    except (InvalidSignature, TypeError, ValueError):
        return failure("wallet governance transparency checkpoint signature verification failed")

    pinned = trusted_log_public_key_b64 is not None
    checks["wallet_governance_transparency_log_integrity"] = {
        "valid": True,
        "entry_count": len(entries),
        "head_entry_sha256": previous_entry_sha256,
        "history_sha256": expected_history_sha256,
    }
    checks["wallet_governance_transparency_signature"] = {
        "valid": True,
        "log_id": bundle["log_id"],
        "signer_key_id": signer_key_id,
    }
    checks["wallet_governance_transparency_anchor"] = {
        "valid": True,
        "pinned": pinned,
        "checkpoint_sequence": cp["checkpoint_sequence"],
        "checkpoint_sha256": checkpoint_sha256,
        "trusted_checkpoint_sha256": trusted_checkpoint_sha256,
        "reason": (
            "latest wallet governance checkpoint is independently pinned"
            if pinned
            else "checkpoint signature is valid but no independent log key/checkpoint pin was supplied"
        ),
    }
    return True, "wallet governance transparency log verified", checks


def verify(
 proof,
 key,
 trusted_governance_policy_sha256=None,
 trusted_wallet_governance_policy_sha256=None,
 trusted_wallet_enrollment_history_sha256=None,
 trusted_wallet_governance_log_public_key=None,
 trusted_wallet_governance_checkpoint_sha256=None,
):
 try:
  trusted_policy_digests = normalize_trusted_governance_policy_digests(
   trusted_governance_policy_sha256
  )
  trusted_wallet_policy_digests = normalize_trusted_governance_policy_digests(
   trusted_wallet_governance_policy_sha256
  )
  trusted_wallet_history_digests = normalize_trusted_governance_policy_digests(
   trusted_wallet_enrollment_history_sha256
  )
  if (trusted_wallet_governance_log_public_key is None) != (trusted_wallet_governance_checkpoint_sha256 is None):
   raise ValueError(
    'wallet governance log public key and checkpoint digest must be supplied together'
   )
  trusted_wallet_log_public_key_b64 = (
   load_trusted_key(trusted_wallet_governance_log_public_key)
   if trusted_wallet_governance_log_public_key is not None else None
  )
 except ValueError as exc:
  return bad(str(exc),{})
 c={}; d=json.loads(Path(proof).read_text(encoding='utf-8')); trusted=load_trusted_key(key); pkg=d.get('package'); ph=d.get('package_sha256')
 c['package_integrity']={'valid':isinstance(pkg,dict) and sha(pkg)==ph}
 if not c['package_integrity']['valid']:return bad('package digest mismatch',c)
 m=pkg.get('manifest'); p=m.get('payload') if isinstance(m,dict) else None
 c['manifest_integrity']={'valid':isinstance(m,dict) and pkg.get('manifest_sha256')==sha(m)}
 if not c['manifest_integrity']['valid']:return bad('manifest digest mismatch',c)
 if pkg.get('protocol')!=PKG or pkg.get('media_type')!=MEDIA or not isinstance(p,dict) or p.get('proof_profile')!='authority_lifecycle':return bad('unsupported proof package',c)
 if pkg.get('proof_protocol')!=PROTOCOL or pkg.get('protocol')!=PKG: return bad('package protocol metadata mismatch',c)
 if not pkg.get('self_contained') or pkg.get('node_count')!=len(p.get('nodes',[])) or pkg.get('edge_count')!=len(p.get('edges',[])): return bad('package graph metadata mismatch',c)
 inventory=[{'type':n.get('type'),'id':n.get('id'),'sha256':n.get('sha256')} for n in p.get('nodes',[])]
 if pkg.get('node_inventory')!=inventory or pkg.get('graph_root_digest')!=p.get('root_digest'): return bad('package graph inventory mismatch',c)
 if pkg.get('assertion_set_sha256')!=sha(pkg.get('assertions',[])): return bad('package assertion-set digest mismatch',c)
 if p.get('proof_profile')=='authority_lifecycle' and pkg.get('required_artifact_types')!=list(REQUIRED_AUTHORITY_TYPES): return bad('authority lifecycle required artifact metadata mismatch',c)
 if p.get('proof_profile')=='authority_lifecycle' and (pkg.get('assertions')!=p.get('authority_assertions') or pkg.get('assertion_set_sha256')!=p.get('authority_assertions_sha256')): return bad('package assertions are not bound to signed manifest',c)
 c['trust_anchor']={'valid':m.get('issuer_public_key_b64')==trusted}
 if not c['trust_anchor']['valid']:return bad('issuer public key is not trusted',c)
 try: pub=Ed25519PublicKey.from_public_bytes(b64(trusted)); pub.verify(b64(m['signature']),canon(p)); sig=True
 except Exception:sig=False
 c['issuer_signature']={'valid':sig}
 if not sig:return bad('invalid manifest signature',c)
 refs=set(); good=True
 for n in p.get('nodes',[]):
  if not isinstance(n,dict) or not all(k in n for k in ('type','id','sha256','data')) or sha(n['data'])!=n['sha256'] or ref(n) in refs:good=False;break
  refs.add(ref(n))
 good=good and all(isinstance(e,dict) and all(k in e for k in ('from','relation','to')) and e['from'] in refs and e['to'] in refs for e in p.get('edges',[])) and root(p)==p.get('root_digest')
 c['graph_integrity']={'valid':good}
 if not good:return bad('graph integrity mismatch',c)
 ok,why=assertions(m); c['authority_protocol']={'valid':ok}
 if not ok:return bad(why,c)
 attestor_node=node(p,'attestor_authority')
 if attestor_node is None:return bad('attestor authority evidence is missing',c)
 governance_ok,governance_reason,historical_attestor=verify_governance(p,attestor_node['id'],attestor_node['data'])
 c['governance_quorum']={'valid':governance_ok,'reason':governance_reason}
 if not governance_ok or historical_attestor is None:return bad(governance_reason,c)
 policy_trust = verify_governance_policy_trust_anchor(
  p, attestor_node['id'], trusted_policy_digests
 )
 c['governance_policy_trust_anchor'] = policy_trust
 if not policy_trust['valid']:return bad(policy_trust['reason'],c)
 a=node(p,'execution_authorization'); r=node(p,'execution_receipt'); ap=a['data']['payload']; rp=r['data']['payload']; t=rp.get('executed_at')
 identity_node=node(p,'identity'); capability_node=node(p,'capability'); intent_node=node(p,'action_intent'); authority_node=node(p,'authority_state'); genesis_node=node(p,'genesis_authority')
 if any(x is None for x in (identity_node,capability_node,intent_node,authority_node,genesis_node)): return bad('authority binding evidence incomplete',c)
 if ap.get('agent_id') != p.get('agent_id') or ap.get('agent_id') != identity_node['data'].get('agent_id') or ap.get('identity_id') != identity_node['id'] or ap.get('capability_id') != capability_node['id'] or ap.get('intent_id') != intent_node['id']:
  return bad('authorization identity/capability/intent binding failed',c)
 if ap.get('action') != intent_node['data']:
  return bad('execution authorization action payload differs from canonical intent',c)
 if rp.get('authorization_sha256') != sha(ap):
  return bad('execution receipt is not bound to the exact execution authorization payload',c)
 external_state_required=bool(ap.get('external_state_required'))
 external_state_scope=rp.get('execution_external_state_scope')
 external_state=ap.get('external_state')
 requirement=ap.get('external_state_requirement')
 if not external_state_required:
  if external_state_scope not in (None,'atomic'):
   return bad('unsupported execution external-state scope',c)
 else:
  if external_state_scope != 'atomic':
   return bad('required external state execution is not atomically enforced',c)
  if not isinstance(external_state,dict) or not external_state:
   return bad('required external state binding is missing',c)
  if not isinstance(requirement,dict):
   return bad('required external state policy requirement is missing',c)
  metadata=intent_node['data'].get('metadata')
  canonical_state=metadata.get('external_state') if isinstance(metadata,dict) else None
  if not isinstance(canonical_state,dict) or external_state != canonical_state:
   return bad('external state binding differs from canonical intent',c)
  if ap.get('external_state_sha256') != sha(external_state):
   return bad('external state fingerprint mismatch',c)
  if ap.get('external_state_requirement_sha256') != sha(requirement):
   return bad('external state requirement fingerprint mismatch',c)
  if external_state.get('kind') != requirement.get('kind'):
   return bad('external state kind does not satisfy policy requirement',c)
  if not isinstance(external_state.get('reference'),str) or not external_state['reference'].strip():
   return bad('external state binding is missing reference',c)
  dv=external_state.get('digest')
  if not isinstance(dv,str) or len(dv)!=64:
   return bad('external state binding has invalid digest',c)
  try: int(dv,16)
  except Exception: return bad('external state binding digest is not hexadecimal',c)
 authority_data=authority_node['data']; authority_sha=sha(authority_data)
 if ap.get('authority_state_sha256') != authority_sha: return bad('historical authority snapshot digest mismatch',c)
 capability_data=capability_node['data']
 authority_obj={'authority_id':f"{ap['agent_id']}:{capability_node['id']}:{authority_data.get('ledger_head_hash') or sha(authority_data)}",'agent_id':ap['agent_id'],'identity_id':ap.get('identity_id',''),'capability_id':capability_node['id'],'capability_version':capability_data.get('version',1),'capability_sha256':ap.get('capability_sha256',''),'state':authority_data['state'],'multiplier':float(authority_data['multiplier']),'epoch':0,'ledger_head_hash':authority_data.get('ledger_head_hash',''),'effective_from':float(authority_data.get('evaluated_at',0.0)),'expires_at':None,'parent_authority_id':None,'evidence_refs':[],'metadata':{'source':'core.authority_state.AuthoritySnapshot','successes':authority_data.get('successes',0),'adverse_events':authority_data.get('adverse_events',0),'critical_events':authority_data.get('critical_events',0),'reason':authority_data.get('reason','')}}
 if genesis_node['data'].get('authority_digest') != sha(authority_obj): return bad('Genesis authority does not bind historical authority',c)
 try:pub.verify(b64(a['data']['signature']),canon(ap)); asig=True
 except Exception:asig=False
 c['authorization']={'valid':asig and ap.get('expires_at',-1)>=t>=ap.get('issued_at',10**30),'historical_verification_time':t}
 if not c['authorization']['valid']:return bad('execution authorization verification failed',c)
 receipt_public_key = pub
 attestation_node = node(p,'outcome_attestation')
 attestation_payload = attestation_node['data'].get('payload',{}) if attestation_node is not None else {}
 if (
  attestation_payload.get('attestor_type') == 'CHAIN_VERIFIER'
  and isinstance(ap.get('agent_id'),str)
  and ap['agent_id'].startswith('anna-installation:')
 ):
  submission_data = rp.get('submission_data')
  if not isinstance(submission_data,dict):
   return bad('Anna CHAIN_VERIFIER receipt is missing wallet enrollment metadata',c)
  wallet_ok,wallet_reason,historical_enrollment,wallet_checks = verify_wallet_enrollment_history(
   p,
   installation_principal=ap['agent_id'],
   chain_id=submission_data.get('chain_id'),
   wallet_address=submission_data.get('sender'),
   attested_at=attestation_payload.get('attested_at'),
   trusted_policy_digests=trusted_wallet_policy_digests,
   trusted_history_digests=trusted_wallet_history_digests,
  )
  c.update(wallet_checks)
  c['wallet_enrollment']={'valid':wallet_ok,'reason':wallet_reason}
  if not wallet_ok or historical_enrollment is None:
   return bad(wallet_reason,c)
  transparency_nodes = [
   item for item in p.get('nodes',[])
   if item.get('type') == 'wallet_governance_transparency_log'
   and isinstance(item.get('data'),dict)
   and item['data'].get('installation_principal') == ap['agent_id']
  ]
  if len(transparency_nodes) > 1:
   return bad('wallet governance transparency evidence is ambiguous',c)
  if not transparency_nodes:
   pinned_requested = (
    trusted_wallet_log_public_key_b64 is not None
    or trusted_wallet_governance_checkpoint_sha256 is not None
   )
   c['wallet_governance_transparency_anchor']={
    'valid':not pinned_requested,
    'pinned':False,
    'reason':(
     'trusted transparency anchor was required but the proof contains no log checkpoint'
     if pinned_requested
     else 'no external wallet governance transparency log was supplied'
    )
   }
   if pinned_requested:
    return bad(c['wallet_governance_transparency_anchor']['reason'],c)
  else:
   transparency_node=transparency_nodes[0]
   transparency_ref=ref(transparency_node)
   if (
    not edge(
     p,
     f"wallet_enrollment_governance_history:{ap['agent_id']}",
     'ANCHORED_BY',
     transparency_ref,
    )
    or transparency_node['id'] != transparency_node['data'].get('checkpoint',{}).get('checkpoint_sha256')
   ):
    return bad('wallet governance history is not linked to its external checkpoint',c)
   history_node = node(p,'wallet_enrollment_governance_history')
   if history_node is None:
    return bad('wallet enrollment history node is missing',c)
   log_ok,log_reason,log_checks=verify_wallet_governance_transparency_bundle(
    transparency_node['data'],
    history_envelopes=history_node['data'].get('envelopes',[]),
    installation_principal=ap['agent_id'],
    trusted_log_public_key_b64=trusted_wallet_log_public_key_b64,
    trusted_checkpoint_sha256=trusted_wallet_governance_checkpoint_sha256,
   )
   c.update(log_checks)
   if not log_ok:
    return bad(log_reason,c)
  wallet_node_id = historical_enrollment['enrollment_id']
  if (
   not edge(p,f"wallet_enrollment_governance_history:{ap['agent_id']}",'COVERS',f"wallet_enrollment:{wallet_node_id}")
   or not edge(p,f"wallet_enrollment:{wallet_node_id}",'AUTHORIZES_RECEIPT',ref(r))
   or rp.get('network') != historical_enrollment.get('network')
  ):
   return bad('wallet enrollment is not bound to the Anna execution receipt',c)
  try:
   receipt_public_key = Ed25519PublicKey.from_public_bytes(
    b64(historical_enrollment['issuer_public_key_b64'])
   )
  except (KeyError,TypeError,ValueError):
   return bad('wallet enrollment issuer public key is invalid',c)
 try:receipt_public_key.verify(b64(r['data']['signature']),canon(rp)); rsig=True
 except Exception:rsig=False
 c['execution']={
  'valid':rsig
  and rp.get('authorization_id')==ap.get('authorization_id')
  and rp.get('intent_id')==ap.get('intent_id')
  and rp.get('agent_id')==ap.get('agent_id')
 }
 if not c['execution']['valid']:return bad('execution receipt verification failed',c)
 l=node(p,'authority_ledger')['data'].get('entries',[]); prev=ZERO; lok=True
 for i,x in enumerate(l,1):
  if x.get('sequence')!=i or x.get('prev_event_hash')!=prev or hashlib.sha256(canon(x.get('event'))).hexdigest()!=x.get('event_hash'):lok=False;break
  prev=x.get('event_hash')
 head=ap.get('authority_ledger_head_hash'); c['historical_authority']={'valid':lok and (head=='0'*64 or any(x.get('event_hash')==head for x in l)),'ledger_sequence':next((i for i,x in enumerate(l,1) if x.get('event_hash')==head),0),'live_ledger_sequence':len(l)}
 if not c['historical_authority']['valid']:return bad('historical authority binding failed',c)
 h_ok,h_reason=verify_historical(authority_data,l,ap.get('authority_policy') or {},head); c['historical_authority_semantics']={'valid':h_ok,'reason':h_reason}
 if not h_ok:return bad('historical authority semantics failed',c)
 cl=node(p,'outcome_claim'); oe=node(p,'observed_effect'); at=node(p,'outcome_attestation'); ev=node(p,'authority_event'); af=node(p,'authority_state_after'); claim_data=cl['data']; observed_data=oe['data']; att_payload=at['data'].get('payload',{});  attestor_signature_ok,attestor_signature_reason=verify_outcome_attestation(at['data'],historical_attestor); c['outcome_attestation_signature']={'valid':attestor_signature_ok,'reason':attestor_signature_reason}; 
 if not attestor_signature_ok:return bad(attestor_signature_reason,c)
 out=edge(p,ref(r),'OBSERVED_BY',ref(cl)) and edge(p,ref(cl),'SUPPORTED_BY',ref(oe)) and claim_data.get('execution_receipt_sha256')==sha(r['data']) and claim_data.get('observed_effect_sha256')==sha(observed_data) and oe['id']==claim_data.get('observed_effect_sha256') and observed_data.get('authorization_id')==ap.get('authorization_id') and observed_data.get('action_sha256')==claim_data.get('action_sha256') and observed_data.get('evidence_ref')==claim_data.get('evidence_ref') and observed_data.get('result_sha256')==claim_data.get('result_sha256') and observed_data.get('observation_sha256')==sha({'verifier_type':observed_data.get('verifier_type'),'evidence_kind':observed_data.get('evidence_kind'),'effect_status':observed_data.get('effect_status'),'authorization_id':observed_data.get('authorization_id'),'action_sha256':observed_data.get('action_sha256'),'observed_at':observed_data.get('observed_at'),'evidence_ref':observed_data.get('evidence_ref'),'result_sha256':observed_data.get('result_sha256'),'observation':observed_data.get('observation')}) and edge(p,ref(at),'ATTESTS',ref(cl)) and att_payload.get('claim_sha256')==sha(claim_data) and att_payload.get('claim')==claim_data; c['outcome']={'valid':out}; learn_ok,learn_reason=verify_learning(claim_data,att_payload,ev['data'],authority_node['data'],af['data'],l,ap.get('authority_policy') or {},ap.get('authority_ledger_head_hash','')); learn=learn_ok; c['learning']={'valid':learn,'reason':learn_reason}
 if not out or not learn:return bad('outcome or learning binding failed',c)
 eh=next((x.get('event_hash') for x in l if x.get('event_id')==ev['data'].get('event_id')),None); c['post_learning_authority']={'valid':eh is not None and af['data'].get('ledger_head_hash')==eh}
 if not c['post_learning_authority']['valid']:return bad('post-learning authority is not ledger-bound',c)
 return {'valid':True,'protocol':PROTOCOL,'root_digest':p['root_digest'],'package_sha256':ph,'assertion_set_sha256':pkg.get('assertion_set_sha256'),'checks':c}
def main():
 x=argparse.ArgumentParser()
 x.add_argument('proof')
 x.add_argument('--public-key',required=True)
 x.add_argument(
  '--trusted-governance-policy-sha256',
  action='append',
  type=trusted_policy_digest_argument,
  default=None,
  metavar='SHA256',
  help=(
   'trusted governance policy digest (repeat for each accepted policy version); '
   'every policy in the attestor lineage must match one supplied digest'
  ),
 )
 x.add_argument(
  '--trusted-wallet-governance-policy-sha256',
  action='append',
  type=trusted_policy_digest_argument,
  default=None,
  metavar='SHA256',
  help='trusted wallet governance policy digest (repeat for every accepted policy version)',
 )
 x.add_argument(
  '--trusted-wallet-enrollment-history-sha256',
  action='append',
  type=trusted_policy_digest_argument,
  default=None,
  metavar='SHA256',
  help='independently trusted wallet enrollment history digest (repeat for each trusted history version)',
 )
 x.add_argument(
  '--wallet-governance-log-public-key',
  default=None,
  metavar='PEM',
  help='independently trusted Ed25519 public key of the wallet governance transparency log',
 )
 x.add_argument(
  '--trusted-wallet-governance-checkpoint-sha256',
  type=trusted_policy_digest_argument,
  default=None,
  metavar='SHA256',
  help='out-of-band digest of the latest signed wallet governance checkpoint',
 )
 x.add_argument('--format',choices=['text','json'],default='text')
 a=x.parse_args()
 try:
  r=verify(
   a.proof,
   a.public_key,
   a.trusted_governance_policy_sha256,
   a.trusted_wallet_governance_policy_sha256,
   a.trusted_wallet_enrollment_history_sha256,
   a.wallet_governance_log_public_key,
   a.trusted_wallet_governance_checkpoint_sha256,
  )
 except Exception as exc:
  r=bad('verification failed closed: '+str(exc),{})
 if a.format=='json':
  print(json.dumps(r,indent=2,sort_keys=True))
 else:
  print('VERIGATE AUTHORITY PROOF - STANDALONE')
  print('Protocol:',r.get('protocol',PROTOCOL))
  for k,v in r.get('checks',{}).items():
   if k in {
    'governance_policy_trust_anchor',
    'wallet_governance_policy_trust_anchor',
    'wallet_enrollment_history_anchor',
    'wallet_governance_transparency_anchor',
   } and not v.get('pinned'):
    status='NOT PINNED'
   else:
    status='PASS' if v.get('valid') else 'FAIL'
   print(f"{k.upper():28} {status}")
  print('RESULT:', 'VALID' if r.get('valid') else 'INVALID')
  if not r.get('valid'):
   print('Reason:',r['reason'])
 return 0 if r.get('valid') else 1
if __name__=='__main__':raise SystemExit(main())

