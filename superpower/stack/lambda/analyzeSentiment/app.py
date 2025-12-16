import base64
import json
import random
import re
import urllib.parse

import boto3

s3 = boto3.client("s3", region_name="ap-northeast-2")
bedrock_nova = boto3.client("bedrock-runtime", region_name="us-east-1")

cors_headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json",
}

EMOTION_POOL = [
    "슬픔",
    "분노",
    "놀람",
    "평온",
    "공포",
    "설렘",
    "피곤",
    "긴장",
    "무관심",
    "희망",
    "안도",
]


def _success(status_code, payload):
    return {"statusCode": status_code, "headers": cors_headers, "body": json.dumps(payload, ensure_ascii=False)}


def _error(status_code, message):
    return _success(status_code, {"message": message})


def _parse_http_body(event):
    body = event.get("body")
    if body is None:
        return {}
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except Exception:
            return {}
    if isinstance(body, str):
        try:
            return json.loads(body)
        except Exception:
            return {}
    if isinstance(body, dict):
        return body
    return {}


def _extract_bucket_key(event):
    if "detail" in event:
        return event["detail"]["bucket"]["name"], urllib.parse.unquote_plus(event["detail"]["object"]["key"])
    body = _parse_http_body(event)
    qs = event.get("queryStringParameters") or {}
    bucket = body.get("bucket") or body.get("Bucket") or qs.get("bucket")
    key = body.get("key") or body.get("Key") or qs.get("key")
    return bucket, key


def _build_request(base64_image):
    instruction = (
        "너는 이미지의 감정을 평가하는 심리분석가다. 반드시 JSON만 반환해라. "
        "항상 joy(기쁨)를 포함한 총 3개의 감정을 돌려줘야 한다. joy 점수는 0~15 정수. "
        "나머지 2개 감정은 이미지에서 느껴지는 감정 중에서 임의로 골라 한국어 이름을 쓰고, 각 점수도 0~15 정수로 준다. "
        '출력 형식: {"emotions":[{"name":"joy","score":int},{"name":"<감정1>","score":int},{"name":"<감정2>","score":int}]} '
        "JSON만 응답하고 불필요한 텍스트는 쓰지 마라."
    )
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": "jpeg",
                            "source": {"bytes": base64_image},
                        }
                    },
                    {"text": instruction},
                ],
            }
        ]
    }


def _clean_score(score):
    try:
        val = int(score)
    except Exception:
        val = 0
    return max(0, min(15, val))


def _parse_emotion_response(text):
    try:
        data = json.loads(text)
        emotions = data.get("emotions") or []
        parsed = []
        for item in emotions:
            name = item.get("name")
            score = _clean_score(item.get("score"))
            if name:
                parsed.append({"name": name, "score": score})
        return parsed
    except Exception:
        return []


def _fallback_emotions():
    others = random.sample(EMOTION_POOL, 2)
    return [
        {"name": "joy", "score": 0},
        {"name": others[0], "score": 0},
        {"name": others[1], "score": 0},
    ]


def lambda_handler(event, context):
    try:
        bucket, key = _extract_bucket_key(event)
        if not bucket or not key:
            return _error(400, "bucket과 key를 전달해야 합니다 (body 혹은 query 혹은 EventBridge detail)")

        print(f"[INFO] Processing file: s3://{bucket}/{key}")
        obj = s3.get_object(Bucket=bucket, Key=key)
        image_bytes = obj["Body"].read()
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        request_body = _build_request(base64_image)
        response = bedrock_nova.invoke_model(
            modelId="amazon.nova-pro-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_body),
        )
        result = json.loads(response["body"].read())
        text = result["output"]["message"]["content"][0]["text"]
        emotions = _parse_emotion_response(text)

        # 보정: joy가 없으면 강제로 추가, 점수 범위 보정
        names = {e["name"] for e in emotions}
        if "joy" not in names:
            emotions.insert(0, {"name": "joy", "score": 0})
        emotions = emotions[:3]
        if len(emotions) < 3:
            # 부족하면 랜덤 감정으로 채우기
            pool = [e for e in EMOTION_POOL if e not in {emo["name"] for emo in emotions}]
            while len(emotions) < 3 and pool:
                emotions.append({"name": pool.pop(), "score": 0})

        # 점수 범위 고정
        for emo in emotions:
            emo["score"] = _clean_score(emo.get("score", 0))

        print(f"[SUCCESS] Emotions: {emotions}")
        return _success(200, {"emotions": emotions})

    except Exception as exc:
        print(f"[ERROR] Failed to analyze emotion: {exc}")
        return _success(200, {"emotions": _fallback_emotions(), "warning": str(exc)})
