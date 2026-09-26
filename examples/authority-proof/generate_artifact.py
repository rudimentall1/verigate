from __future__ import annotations
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from attest.keys import load_public_key
from cryptography.hazmat.primitives import serialization
from core.proof_package import build_proof_package, serialize_proof_package
from tests.test_reference_lifecycle import VerigateReferenceLifecycleTest
OUT = ROOT / 'examples' / 'authority-proof'
def main():
    case = VerigateReferenceLifecycleTest(methodName='_valid_manifest')
    case.setUp()
    try:
        manifest = case._valid_manifest(policy_source_ref='examples/authority-proof/policy.yaml')
        package = build_proof_package(manifest)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'authority-proof.json').write_bytes(serialize_proof_package(package) + b'\n')
        public_key = load_public_key(case.public_path)
        (OUT / 'issuer.pub').write_bytes(public_key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        print('generated portable artifact')
    finally:
        case.tearDown()
if __name__ == '__main__':
    main()
