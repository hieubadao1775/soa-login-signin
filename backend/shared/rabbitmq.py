import json
import uuid
from datetime import datetime, timezone

import pika


def publish_event(
    rabbitmq_url: str,
    event_type: str,
    payload: dict,
    exchange: str = "recruitment.events",
    routing_key: str = "recruitment.event",
) -> bool:
    message = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }

    try:
        params = pika.URLParameters(rabbitmq_url)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
        connection.close()
        return True
    except Exception as exc:
        print(f"[rabbitmq] publish failed for {event_type}: {exc}")
        return False
