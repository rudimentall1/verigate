#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,hashlib,json
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
PROTOCOL='verigate-authority-proof-v1'; PKG='verigate-proof-package-v1'; MEDIA='application/vnd.verigate.proof-package+json'; ZERO='0'*64
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
 p=m['payload']; kinds=['identity','capability','action_intent','authority_state','genesis_authority','decision','execution_authorization','execution_receipt','outcome_claim','outcome_attestation','authority_event','authority_state_after','authority_ledger']; n={k:node(p,k) for k in kinds}
 if any(v is None for v in n.values()): return False,'authority protocol evidence incomplete'
 R={k:ref(v) for k,v in n.items()}; ap=n['execution_authorization']['data']['payload']; rp=n['execution_receipt']['data']['payload']; cp=n['outcome_claim']['data']; ep=n['authority_event']['data']; sp=n['authority_state_after']['data']; ent=n['authority_ledger']['data'].get('entries',[])
 def A(i,k,s,pr,o,e):
  x={'id':i,'kind':k,'subject':s,'predicate':pr,'object':o,'evidence':e}; x['sha256']=hashlib.sha256(canon(x)).hexdigest(); return x
 exp=[A('A1','identity',R['identity'],'possessed_capability',R['capability'],[R['identity'],R['capability']]),A('A2','intent',R['action_intent'],'proposed_by',n['identity']['data'].get('agent_id',p.get('agent_id')),[R['action_intent'],R['identity']]),A('A3','authority',R['authority_state'],'permitted',R['action_intent'],[R['authority_state'],R['action_intent'],R['capability']]),A('A4','authorization',R['execution_authorization'],'derived_from',R['authority_state'],[R['decision'],R['execution_authorization'],R['authority_state'],R['genesis_authority']]),A('A5','execution',R['execution_receipt'],'consumed_authorization',R['execution_authorization'],[R['execution_authorization'],R['execution_receipt']]),A('A6','observation',R['outcome_claim'],'observes',R['execution_receipt'],[R['execution_receipt'],R['outcome_claim'],R['outcome_attestation']]),A('A7','learning',R['authority_event'],'justified_by',R['outcome_claim'],[R['outcome_claim'],R['authority_event']]),A('A8','learning',R['authority_state_after'],'produced_by',R['authority_event'],[R['authority_event'],R['authority_state_after']]),A('A9','integrity',R['authority_state_after'],'ledger_bound',R['authority_ledger'],[R['authority_state_after'],R['authority_ledger']])]
 checks=[edge(p,R['identity'],'AUTHENTICATES',R['action_intent']),edge(p,R['capability'],'AUTHORIZES',R['action_intent']),ap.get('authority_state_sha256')==sha(n['authority_state']['data']),edge(p,R['decision'],'MINTS',R['execution_authorization']),edge(p,R['execution_authorization'],'PRODUCES',R['execution_receipt']),rp.get('authorization_id')==ap.get('authorization_id'),edge(p,R['execution_receipt'],'OBSERVED_BY',R['outcome_claim']),edge(p,R['outcome_attestation'],'ATTESTS',R['outcome_claim']),edge(p,R['outcome_claim'],'INFORMS',R['authority_event']),edge(p,R['authority_event'],'TRANSITIONS_TO',R['authority_state_after']),ep.get('evidence_ref')==cp.get('claim_id'),sp.get('source_event_id')==ep.get('event_id'),len([x for x in ent if x.get('event_id')==ep.get('event_id')])==1 and sp.get('ledger_head_hash')==next((x.get('event_hash') for x in ent if x.get('event_id')==ep.get('event_id')),None)]
 return (exp==p.get('authority_assertions') and all(checks) and sha(exp)==p.get('authority_assertions_sha256'),'signed authority assertions do not match evidence' if exp!=p.get('authority_assertions') else 'authority protocol preconditions failed')
def verify(proof,key):
 c={}; d=json.loads(Path(proof).read_text()); kt=Path(key).read_text().strip(); der=base64.b64decode(''.join(x for x in kt.splitlines() if 'PUBLIC KEY' not in x)); trusted=base64.b64encode(der[-32:]).decode(); pkg=d.get('package'); ph=d.get('package_sha256')
 c['package_integrity']={'valid':isinstance(pkg,dict) and sha(pkg)==ph}
 if not c['package_integrity']['valid']:return bad('package digest mismatch',c)
 m=pkg.get('manifest'); p=m.get('payload') if isinstance(m,dict) else None
 c['manifest_integrity']={'valid':isinstance(m,dict) and pkg.get('manifest_sha256')==sha(m)}
 if not c['manifest_integrity']['valid']:return bad('manifest digest mismatch',c)
 if pkg.get('protocol')!=PKG or pkg.get('media_type')!=MEDIA or not isinstance(p,dict) or p.get('proof_profile')!='authority_lifecycle':return bad('unsupported proof package',c)
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
 a=node(p,'execution_authorization'); r=node(p,'execution_receipt'); ap=a['data']['payload']; rp=r['data']['payload']; t=rp.get('executed_at')
 try:pub.verify(b64(a['data']['signature']),canon(ap)); asig=True
 except Exception:asig=False
 c['authorization']={'valid':asig and ap.get('expires_at',-1)>=t>=ap.get('issued_at',10**30),'historical_verification_time':t}
 if not c['authorization']['valid']:return bad('execution authorization verification failed',c)
 try:pub.verify(b64(r['data']['signature']),canon(rp)); rsig=True
 except Exception:rsig=False
 c['execution']={'valid':rsig and rp.get('authorization_id')==ap.get('authorization_id') and rp.get('intent_id')==ap.get('intent_id')}
 if not c['execution']['valid']:return bad('execution receipt verification failed',c)
 l=node(p,'authority_ledger')['data'].get('entries',[]); prev=ZERO; lok=True
 for i,x in enumerate(l,1):
  if x.get('sequence')!=i or x.get('prev_event_hash')!=prev or hashlib.sha256(canon(x.get('event'))).hexdigest()!=x.get('event_hash'):lok=False;break
  prev=x.get('event_hash')
 head=ap.get('authority_ledger_head_hash'); c['historical_authority']={'valid':lok and (head=='0'*64 or any(x.get('event_hash')==head for x in l)),'ledger_sequence':next((i for i,x in enumerate(l,1) if x.get('event_hash')==head),0),'live_ledger_sequence':len(l)}
 if not c['historical_authority']['valid']:return bad('historical authority binding failed',c)
 cl=node(p,'outcome_claim'); at=node(p,'outcome_attestation'); ev=node(p,'authority_event'); af=node(p,'authority_state_after'); out=edge(p,ref(r),'OBSERVED_BY',ref(cl)) and edge(p,ref(at),'ATTESTS',ref(cl)); learn=ev['data'].get('evidence_ref')==cl['data'].get('claim_id') and af['data'].get('source_event_id')==ev['data'].get('event_id'); c['outcome']={'valid':out}; c['learning']={'valid':learn}
 if not out or not learn:return bad('outcome or learning binding failed',c)
 eh=next((x.get('event_hash') for x in l if x.get('event_id')==ev['data'].get('event_id')),None); c['post_learning_authority']={'valid':eh is not None and af['data'].get('ledger_head_hash')==eh}
 if not c['post_learning_authority']['valid']:return bad('post-learning authority is not ledger-bound',c)
 return {'valid':True,'protocol':PROTOCOL,'root_digest':p['root_digest'],'package_sha256':ph,'assertion_set_sha256':pkg.get('assertion_set_sha256'),'checks':c}
def main():
 x=argparse.ArgumentParser();x.add_argument('proof');x.add_argument('--public-key',required=True);x.add_argument('--format',choices=['text','json'],default='text');a=x.parse_args();r=verify(a.proof,a.public_key)
 if a.format=='json':print(json.dumps(r,indent=2,sort_keys=True))
 else:
  print('VERIGATE AUTHORITY PROOF — STANDALONE');print('Protocol:',r.get('protocol',PROTOCOL));[print(f"{k.upper():28} {'PASS' if v.get('valid') else 'FAIL'}") for k,v in r.get('checks',{}).items()];print('RESULT:', 'VALID' if r.get('valid') else 'INVALID'); print('Reason:',r['reason']) if not r.get('valid') else None
 return 0 if r.get('valid') else 1
if __name__=='__main__':raise SystemExit(main())



