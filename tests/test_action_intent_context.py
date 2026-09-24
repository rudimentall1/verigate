from core.models import ActionIntent


def test_action_intent_context_is_first_class_and_serialized():
    intent = ActionIntent(
        agent_id="agent-1",
        action_type="api.request",
        target="payments",
        resource="/v1/payments",
        purpose="invoice settlement",
        declared_context={"invoice_id": "INV-42", "environment": "production"},
        parent_intent_id="intent-parent",
        requested_capability="payments.execute",
        constraints={"max_amount": 100},
    )

    data = intent.as_dict()

    assert data["purpose"] == "invoice settlement"
    assert data["declared_context"]["invoice_id"] == "INV-42"
    assert data["parent_intent_id"] == "intent-parent"
    assert data["requested_capability"] == "payments.execute"
    assert data["constraints"]["max_amount"] == 100
