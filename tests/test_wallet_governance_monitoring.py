import unittest

from core.wallet_governance_monitoring import build_wallet_governance_outbox_health


class WalletGovernanceOutboxMonitoringTests(unittest.TestCase):
    def test_empty_outbox_is_healthy(self):
        report = build_wallet_governance_outbox_health([], now=1000)
        self.assertEqual(report["status"], "HEALTHY")
        self.assertEqual(report["metrics"]["pending_count"], 0)
        self.assertIsNone(report["metrics"]["oldest_pending_age_seconds"])

    def test_pending_age_attempts_and_principals_are_reported(self):
        events = [
            {
                "action_id": "a1",
                "installation_principal": "principal-a",
                "status": "PENDING",
                "attempts": 3,
                "created_at": 700,
                "last_error": "connection refused",
            },
            {
                "action_id": "a2",
                "installation_principal": "principal-a",
                "status": "PENDING",
                "attempts": 1,
                "created_at": 900,
                "last_error": None,
            },
            {
                "action_id": "a3",
                "installation_principal": "principal-b",
                "status": "DELIVERED",
                "attempts": 1,
                "created_at": 500,
                "delivered_at": 600,
            },
        ]
        report = build_wallet_governance_outbox_health(
            events,
            now=1000,
            max_pending_age_seconds=200,
            max_pending_count=5,
            max_attempts=5,
        )
        self.assertEqual(report["status"], "DEGRADED")
        self.assertEqual(report["metrics"]["pending_count"], 2)
        self.assertEqual(report["metrics"]["delivered_count"], 1)
        self.assertEqual(report["metrics"]["oldest_pending_age_seconds"], 300)
        self.assertEqual(report["metrics"]["max_pending_attempts"], 3)
        self.assertEqual(report["metrics"]["pending_principal_count"], 1)
        self.assertEqual(report["alerts"], ["OLDEST_PENDING_EVENT_TOO_OLD"])

    def test_multiple_threshold_breaches_are_reported_deterministically(self):
        events = [
            {
                "action_id": "a1",
                "installation_principal": "principal-a",
                "status": "PENDING",
                "attempts": 8,
                "created_at": 0,
                "last_error": "timeout",
            },
            {
                "action_id": "a2",
                "installation_principal": "principal-b",
                "status": "PENDING",
                "attempts": 2,
                "created_at": 0,
            },
        ]
        report = build_wallet_governance_outbox_health(
            events,
            now=1000,
            max_pending_age_seconds=100,
            max_pending_count=1,
            max_attempts=5,
        )
        self.assertEqual(
            report["alerts"],
            [
                "PENDING_QUEUE_TOO_LARGE",
                "OLDEST_PENDING_EVENT_TOO_OLD",
                "PENDING_EVENT_RETRY_LIMIT_EXCEEDED",
            ],
        )
        self.assertEqual(report["status"], "UNHEALTHY")

    def test_invalid_events_and_thresholds_fail_closed(self):
        with self.assertRaises(ValueError):
            build_wallet_governance_outbox_health(
                [{"status": "UNKNOWN"}],
                now=100,
            )
        with self.assertRaises(ValueError):
            build_wallet_governance_outbox_health(
                [],
                max_pending_count=0,
            )


if __name__ == "__main__":
    unittest.main()
