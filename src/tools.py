"""Mock tools the agent can call. Deterministic so eval runs are repeatable."""

STATUSES = ["placed", "shipped", "delivered", "delayed"]

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Look up the current status, carrier, and ETA for an order by its order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "integer",
                        "description": "The numeric order ID, e.g. 4521",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]


def get_order_status(order_id: int) -> dict:
    status = STATUSES[order_id % len(STATUSES)]
    eta_days = (order_id % 7) + 1
    return {
        "order_id": order_id,
        "status": status,
        "eta_days": eta_days,
        "carrier": "UPS" if order_id % 2 == 0 else "FedEx",
    }


TOOL_IMPLS = {
    "get_order_status": get_order_status,
}
