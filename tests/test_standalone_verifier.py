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
