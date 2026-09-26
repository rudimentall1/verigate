import json, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'tools'/'verigate_proof_verifier.py'
PROOF=ROOT/'examples'/'authority-proof'/'authority-proof.json'
KEY=ROOT/'examples'/'authority-proof'/'issuer.pub'
def run(path): return subprocess.run([sys.executable,str(SCRIPT),str(path),'--public-key',str(KEY),'--format','json'],cwd=ROOT,text=True,capture_output=True)
def test_standalone_reference_vector_is_valid():
 r=run(PROOF); assert r.returncode==0, r.stdout+r.stderr; assert json.loads(r.stdout)['valid'] is True
def test_standalone_rejects_tamper():
 d=json.loads(PROOF.read_text()); d['package']['agent_id']='tampered-agent'
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'tampered.json'; p.write_text(json.dumps(d)); r=run(p); assert r.returncode!=0; assert json.loads(r.stdout)['valid'] is False
def test_standalone_has_no_runtime_imports():
 s=SCRIPT.read_text(); assert 'from core' not in s and 'import core' not in s and 'from attest' not in s and 'import attest' not in s


def test_standalone_fails_closed_on_invalid_json():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"invalid.json"; p.write_text("{not-json")
        r=run(p); assert r.returncode!=0
        result=json.loads(r.stdout)
        assert result["valid"] is False
        assert "verification failed closed" in result["reason"]

def test_standalone_fails_closed_on_invalid_public_key():
    with tempfile.TemporaryDirectory() as td:
        key=Path(td)/"bad.pub"; key.write_text("not-a-public-key")
        r=subprocess.run([sys.executable,str(SCRIPT),str(PROOF),"--public-key",str(key),"--format","json"],cwd=ROOT,text=True,capture_output=True)
        assert r.returncode!=0
        result=json.loads(r.stdout)
        assert result["valid"] is False
        assert "verification failed closed" in result["reason"]

def _assert_invalid_mutation(mutator):
    d=json.loads(PROOF.read_text())
    mutator(d)
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"mutated.json"; p.write_text(json.dumps(d))
        r=run(p)
        result=json.loads(r.stdout)
        assert r.returncode!=0, r.stdout
        assert result["valid"] is False, r.stdout

def test_standalone_mutation_matrix_package_metadata():
    _assert_invalid_mutation(lambda d: d["package"].__setitem__("protocol","tampered"))

def test_standalone_mutation_matrix_manifest_payload():
    _assert_invalid_mutation(lambda d: d["package"]["manifest"]["payload"].__setitem__("agent_id","tampered-agent"))

def test_standalone_mutation_matrix_assertions():
    _assert_invalid_mutation(lambda d: d["package"]["manifest"]["payload"]["authority_assertions"][0].__setitem__("predicate","tampered"))

def test_standalone_mutation_matrix_graph_inventory():
    _assert_invalid_mutation(lambda d: d["package"]["node_inventory"][0].__setitem__("sha256","0"*64))

def test_standalone_mutation_matrix_trust_anchor():
    d=json.loads(PROOF.read_text())
    with tempfile.TemporaryDirectory() as td:
        proof=Path(td)/"proof.json"; proof.write_text(json.dumps(d))
        key=Path(td)/"bad.pub"; key.write_text(KEY.read_text().replace("A","B",1))
        r=subprocess.run([sys.executable,str(SCRIPT),str(proof),"--public-key",str(key),"--format","json"],cwd=ROOT,text=True,capture_output=True)
        assert r.returncode!=0
        assert json.loads(r.stdout)["valid"] is False


def test_standalone_semantic_conformance_mutation_matrix():
    from tests.test_reference_lifecycle import VerigateReferenceLifecycleTest
    from core.proof_engine import canonical, digest
    from core.evidence_manifest import graph_root
    from core.proof_package import build_proof_package
    from cryptography.hazmat.primitives import serialization
    import base64, hashlib
    case=VerigateReferenceLifecycleTest(); case.setUp()
    try:
        original=case._valid_manifest(policy_source_ref="examples/authority-proof/policy.yaml")
        base=build_proof_package(original)
        def node(p,k): return next(n for n in p["nodes"] if n["type"]==k)
        mutations=[
            ("capability",lambda p: node(p,"execution_authorization")["data"]["payload"].__setitem__("capability_id","forged-capability")),
            ("identity",lambda p: node(p,"execution_authorization")["data"]["payload"].__setitem__("identity_id","forged-identity")),
            ("authority",lambda p: node(p,"authority_state")["data"].__setitem__("multiplier",0.01)),
            ("genesis",lambda p: node(p,"genesis_authority")["data"].__setitem__("authority_digest","00"*32)),
            ("receipt",lambda p: node(p,"execution_receipt")["data"]["payload"].__setitem__("authorization_id","forged-auth")),
            ("claim",lambda p: node(p,"outcome_claim")["data"].__setitem__("execution_receipt_sha256","00"*32)),
            ("learning",lambda p: node(p,"authority_event")["data"].__setitem__("evidence_ref","forged-claim")),
            ("post-learning",lambda p: node(p,"authority_state_after")["data"].__setitem__("source_event_id","forged-event")),
            ("edge",lambda p: next(e for e in p["edges"] if e["relation"]=="AUTHORIZES").__setitem__("to","action_intent:forged-intent")),
        ]
        for label,mutation in mutations:
            package=json.loads(json.dumps(base)); m=package["package"]["manifest"]; mutation(m["payload"])
            for n in m["payload"]["nodes"]:
                n["sha256"]=hashlib.sha256(canonical(n["data"])).hexdigest()
            m["payload"]["root_digest"]=graph_root(m["payload"])
            m["signature"]=base64.b64encode(case.private_key.sign(canonical(m["payload"]))).decode()
            package["package"]["manifest_sha256"]=digest(m)
            package["package"]["graph_root_digest"]=m["payload"]["root_digest"]
            package["package"]["node_inventory"]=[{"type":n["type"],"id":n["id"],"sha256":n["sha256"]} for n in m["payload"]["nodes"]]
            package["package_sha256"]=digest(package["package"])
            with tempfile.TemporaryDirectory() as td:
                proof=Path(td)/"semantic.json"; key=Path(td)/"issuer.pub"
                proof.write_bytes(canonical(package))
                key.write_bytes(case.public_key.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
                r=subprocess.run([sys.executable,str(SCRIPT),str(proof),"--public-key",str(key),"--format","json"],cwd=ROOT,text=True,capture_output=True)
                result=json.loads(r.stdout)
                assert r.returncode!=0, label+"\n"+r.stdout
                assert result["valid"] is False, label+"\n"+r.stdout
    finally: case.tearDown()
