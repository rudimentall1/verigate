from decimal import Decimal

from core.models import ActionIntent, Capability


def test_capability_limit_uses_exact_amount() -> None:
    capability = Capability(
        capability_id="cap-1",
        agent_id="agent-1",
        allowed_actions=("payment",),
        allowed_assets=("EUR",),
        max_per_action={"EUR": 0.1},
    )
    action = ActionIntent(
        agent_id="agent-1",
        action_type="payment",
        target="merchant",
        amount=Decimal("0.100000000000000001"),
        amount_exact="0.100000000000000001",
        asset="EUR",
    )

    permitted, reason = capability.permits(action)

    assert not permitted
    assert reason == "action exceeds capability limit"
