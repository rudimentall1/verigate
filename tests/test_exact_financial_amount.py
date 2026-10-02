from decimal import Decimal

from core.models import ActionIntent
from core.money import exceeds
from core.policy import Policy
from core.rules import check_generic_amount_cap


def test_exact_amount_is_authoritative_for_action_caps() -> None:
    action = ActionIntent(
        agent_id="agent-1",
        action_type="payment",
        target="merchant",
        amount=Decimal("0.100000000000000001"),
        amount_exact="0.100000000000000001",
        asset="EUR",
    )
    policy = Policy(per_tx_cap={"EUR": 0.1})

    match = check_generic_amount_cap(action, policy)

    assert match is not None
    assert match.rule_id == "per_tx_cap_exceeded"


def test_exact_amount_preserves_decimal_in_signed_intent_shape() -> None:
    action = ActionIntent(
        agent_id="agent-1",
        action_type="payment",
        target="merchant",
        amount=Decimal("0.100000000000000001"),
        amount_exact="0.100000000000000001",
        asset="EUR",
    )

    payload = action.as_dict()

    assert payload["amount"] == "0.100000000000000001"
    assert payload["amount_exact"] == "0.100000000000000001"


def test_legacy_float_amount_remains_supported() -> None:
    assert exceeds(0.1, 0.1) is False
