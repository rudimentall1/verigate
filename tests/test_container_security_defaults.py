"""Regression checks for the secure-by-default container deployment."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ContainerSecurityDefaultsTest(unittest.TestCase):
    def test_docker_image_requires_api_auth_and_signed_intents(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("VERIGATE_REQUIRE_AUTH=1", dockerfile)
        self.assertIn("VERIGATE_REQUIRE_SIGNED_INTENT=1", dockerfile)

    def test_compose_requires_api_key_and_only_binds_loopback(self) -> None:
        compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        service = compose["services"]["verigate"]

        self.assertEqual(service["ports"], ["127.0.0.1:8000:8000"])
        environment = service["environment"]
        self.assertEqual(environment["VERIGATE_REQUIRE_AUTH"], "1")
        self.assertEqual(environment["VERIGATE_REQUIRE_SIGNED_INTENT"], "1")
        self.assertIn("?Set VERIGATE_API_KEYS", environment["VERIGATE_API_KEYS"])

    def test_docker_context_excludes_local_workspace_artifacts(self) -> None:
        ignored = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
        self.assertIn("_tools/", ignored)
        self.assertIn("_anna-screen.png", ignored)


if __name__ == "__main__":
    unittest.main()
