import copy
import unittest

from enforcement.protocol import _issue_execution_permit


class ExecutionPermitTest(unittest.TestCase):
    def _authorization(self):
        return {
            "algorithm": "Ed25519",
            "payload": {
                "authorization_id": "a" * 64,
                "nonce": "nonce-1",
                "action": {
                    "network": "solana",
                    "target": "recipient-original",
                    "amount": 0.001,
                },
            },
            "signature": "signed-envelope",
        }

    def test_permit_rejects_action_mutation_after_issuance(self):
        authorization = self._authorization()
        permit = _issue_execution_permit(authorization)
        tampered = copy.deepcopy(authorization)
        tampered["payload"]["action"]["target"] = "attacker-recipient"

        with self.assertRaisesRegex(PermissionError, "exact authorization envelope"):
            permit.claim(tampered)

        # A rejected mismatched claim must not burn the valid permit.
        permit.claim(authorization)

    def test_permit_rejects_signature_or_algorithm_mutation(self):
        authorization = self._authorization()
        permit = _issue_execution_permit(authorization)
        tampered = copy.deepcopy(authorization)
        tampered["signature"] = "different-signature"

        with self.assertRaisesRegex(PermissionError, "exact authorization envelope"):
            permit.claim(tampered)

    def test_permit_is_one_shot_for_the_exact_envelope(self):
        authorization = self._authorization()
        permit = _issue_execution_permit(authorization)
        permit.claim(authorization)

        with self.assertRaisesRegex(PermissionError, "already used"):
            permit.claim(authorization)


if __name__ == "__main__":
    unittest.main()
