import json
import os
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "ap-northeast-2")

def lambda_handler(event, context):  # pylint: disable=unused-argument
    print("Received event:", json.dumps(event))
    try:
        connection_id = _extract_connection_id(event)
        print(f"[DEBUG] connection_id={connection_id}")
        return {
            "statusCode": 200,
            "body": json.dumps(
                {"message": "Connection acknowledged", "connectionId": connection_id}
            ),
        }
    except ValueError as exc:
        print("Missing connectionId:", exc)
        return {"statusCode": 400, "body": json.dumps({"error": str(exc)})}
    except ClientError as exc:
        print("Failed to notify client:", exc)
        status = exc.response["ResponseMetadata"].get("HTTPStatusCode", 500)
        return {"statusCode": status, "body": json.dumps({"error": str(exc)})}


def _extract_connection_id(event: dict) -> str:
    candidates = [
        event.get("connectionId"),
        event.get("detail", {}).get("connectionId"),
        event.get("requestContext", {}).get("connectionId"),
    ]

    records = event.get("Records") or []
    if records:
        candidates.append(records[0].get("connectionId"))
        candidates.append(records[0].get("message", {}).get("connectionId"))

    for candidate in candidates:
        if candidate:
            return candidate

    raise ValueError("connectionId missing in event payload")