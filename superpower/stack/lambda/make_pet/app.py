import base64
import json
import random
import re
import time
import urllib.parse

import boto3

s3 = boto3.client('s3', region_name='ap-northeast-2')
bedrock_nova = boto3.client("bedrock-runtime", region_name="us-east-1")
bedrock_canvas = boto3.client("bedrock-runtime", region_name="us-east-1")

cors_headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json",
}


def _parse_http_body(event):
    """Parse JSON body from API Gateway event; handles base64 encoding."""
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


def _success(status_code, payload):
    return {"statusCode": status_code, "headers": cors_headers, "body": json.dumps(payload)}


def _error(status_code, message):
    return _success(status_code, {"message": message})


def _sanitize_text_for_generation(text, max_length=400):
    """Bedrock 프롬프트를 정제한다."""
    if not isinstance(text, str):
        text = ""
    cleaned = text.replace("**", " ")
    cleaned = re.sub(r"[#*_`>-]+", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned[:max_length]


def _safe_metadata_value(value, max_length=200):
    """S3 메타데이터는 ASCII만 허용하므로 안전 문자열로 변환한다."""
    if not isinstance(value, str):
        return "unknown"
    ascii_only = value.encode("ascii", errors="ignore").decode("ascii")
    ascii_only = " ".join(ascii_only.split())
    if not ascii_only:
        ascii_only = "unknown"
    return ascii_only[:max_length]


def lambda_handler(event, context):
    try:
        # 1. 이벤트 유형에 따라 버킷 이름과 객체 키 추출 (EventBridge or API Gateway)
        if "detail" in event:
            bucket = event["detail"]["bucket"]["name"]
            key = urllib.parse.unquote_plus(event["detail"]["object"]["key"])
        else:
            body = _parse_http_body(event)
            query_params = event.get("queryStringParameters") or {}
            bucket = body.get("bucket") or body.get("Bucket") or query_params.get("bucket")
            key = body.get("key") or body.get("Key") or query_params.get("key")
            if not bucket or not key:
                return _error(400, "bucket과 key를 전달해야 합니다 (body 혹은 query)")
        print(f"Processing file: s3://{bucket}/{key}")

        # 2. 업로드된 이미지 가져와서 분석
        print(f"Analyzing uploaded image and generating related AI image...")
        
        # S3에서 업로드된 이미지 가져오기
        response = s3.get_object(Bucket=bucket, Key=key)
        original_image_data = response['Body'].read()
        original_image_base64 = base64.b64encode(original_image_data).decode('utf-8')
        
        # 업로드된 이미지 분석 후 연관 이미지 생성
        try:
            start_time = time.time()
            
            # 1단계: Nova Pro를 사용해 이미지 분석 (us-east-1에서 호출)
            analysis_request = {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": {
                                    "format": "jpeg",
                                    "source": {
                                        "bytes": original_image_base64
                                    }
                                }
                            },
                            {
                                "text": "성장형 게임에서 사용할 아기 펫 이미지를 생성하기 위해 전달 된 이미지를 분석 후 그것을 바탕으로 생성할 아기 펫에 대해 구체적으로 설명해줘"
                            }
                        ]
                    }
                ]
            }
            
            # Nova Pro로 이미지 분석
            analysis_response = bedrock_nova.invoke_model(
                modelId="amazon.nova-pro-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(analysis_request)
            )
            
            analysis_result = json.loads(analysis_response["body"].read())
            analyzed_prompt = analysis_result["output"]["message"]["content"][0]["text"].strip()    

            # 1. System Prompt에 명확한 JSON 스키마와 지시사항을 정의합니다.
            system_instruction = """
            당신은 Nova Canvas를 위한 전문 프롬프트 엔지니어입니다.
            사용자의 입력을 바탕으로 이미지 생성용 프롬프트를 작성하세요.

            [제약 사항]
            1. 스타일: SOFT_DIGITAL_PAINTING
            2. 출력 형식: 오직 유효한 JSON 포맷으로만 응답하세요. Markdown, 코드 블록(```json), 기타 설명을 포함하지 마세요.
            3. JSON 스키마:
            {
                "text": "영문으로 작성된 실제 이미지 생성 프롬프트 (1~2문장)",
                "navigationText": "사용자에게 보여줄 한글 안내 문구 (매우 짧고 간결하게)"
            }
            """

            llm_prompt_request = {
                "system": [{"text": system_instruction}],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    "아래 분석 텍스트를 기반으로 캐릭터(아기 펫, 중앙 배치)를 포함한 프롬프트를 만들어줘.\n"
                                    f"분석 텍스트: {analyzed_prompt}"
                                )
                            }
                        ],
                    }
                ],
                # inferenceConfig를 통해 랜덤성을 줄여 구조적 안정성을 높입니다.
                "inferenceConfig": {
                    "temperature": 0.0,  # 포맷 준수를 위해 0에 가깝게 설정
                    "topP": 0.9,
                    "maxTokens": 1000
                }
            }

            try:
                llm_response = bedrock_nova.invoke_model(
                    modelId="amazon.nova-pro-v1:0",
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(llm_prompt_request),
                )
                
                llm_result = json.loads(llm_response["body"].read())
                response_text = llm_result["output"]["message"]["content"][0]["text"].strip()
                
                # [중요] 응답이 혹시 마크다운 코드블록(```json ...)으로 감싸져 있을 경우를 대비한 클린업
                if response_text.startswith("```json"):
                    response_text = response_text.replace("```json", "").replace("```", "").strip()
                elif response_text.startswith("```"):
                    response_text = response_text.replace("```", "").strip()

                # 문자열을 JSON 객체로 파싱
                structured_data = json.loads(response_text)
                
                print(f"[INFO] Text: {structured_data.get('text')}")
                print(f"[INFO] Navigation: {structured_data.get('navigationText')}")

            except json.JSONDecodeError:
                print(f"[ERROR] 모델이 올바른 JSON을 반환하지 않았습니다. 응답: {response_text}")
            except Exception as transform_error:
                print(f"[WARNING] 처리 중 오류 발생: {transform_error}")


            # 2단계: 분석 결과를 바탕으로 Nova Canvas로 연관 이미지 생성
            canvas_request = {
                "taskType": "TEXT_IMAGE",
                "textToImageParams": {
                    "text": structured_data.get('text'),
                    "negativeText": structured_data.get('navigationText'),
                    "style": "SOFT_DIGITAL_PAINTING",
                },
                "imageGenerationConfig": {
                    "numberOfImages": 1,
                    "width": 1024,
                    "height": 1024
                }
            }
            
            # Nova Canvas는 us-east-1에서 제공됨
            canvas_response = bedrock_canvas.invoke_model(
                modelId="amazon.nova-canvas-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(canvas_request)
            )
            
            canvas_result = json.loads(canvas_response["body"].read())
            base64_image_data = canvas_result.get("images") or canvas_result.get("image")
            if isinstance(base64_image_data, list):
                first_image = base64_image_data[0] if base64_image_data else None
                if isinstance(first_image, dict):
                    base64_image_data = first_image.get("base64") or first_image.get("image") or first_image.get("data")
                else:
                    base64_image_data = first_image
            elif isinstance(base64_image_data, dict):
                base64_image_data = base64_image_data.get("base64") or base64_image_data.get("image") or base64_image_data.get("data")
            if not base64_image_data:
                raise ValueError("Nova Canvas response did not include an image")
            generated_image_data = base64.b64decode(base64_image_data)
            
            generation_time = time.time() - start_time
            print(f"[SUCCESS] Related AI image generated with Nova Canvas in {generation_time:.2f} seconds")
            
            selected_prompt = structured_data.get('text')
                
        except Exception as bedrock_error:
            print(f"[WARNING] Bedrock analysis/generation failed: {bedrock_error}")
            # 분석 실패 시 원본 파일 사용하고 기본 프롬프트로 새 이미지 생성
            fallback_prompts = [
                "A creative artistic interpretation with vibrant colors",
                "An abstract artistic version with modern style",
                "A fantasy reimagining with magical elements",
                "A minimalist artistic interpretation",
                "A surreal artistic transformation"
            ]
            
            try:
                fallback_prompt = random.choice(fallback_prompts)
                fallback_request = {
                    "taskType": "TEXT_IMAGE",
                    "textToImageParams": {
                        "text": fallback_prompt,
                        "negativeText": "real human baby, realistic adult features, extra limbs, distorted anatomy, scary expression, cluttered background",
                        "style": "SOFT_DIGITAL_PAINTING",
                    },
                    "imageGenerationConfig": {
                        "numberOfImages": 1,
                        "width": 1024,
                        "height": 1024
                    }
                }
                
                fallback_response = bedrock_canvas.invoke_model(
                    modelId="amazon.nova-canvas-v1:0",
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(fallback_request)
                )
                
                fallback_result = json.loads(fallback_response["body"].read())
                base64_image_data = fallback_result.get("images") or fallback_result.get("image")
                if isinstance(base64_image_data, list):
                    first_image = base64_image_data[0] if base64_image_data else None
                    if isinstance(first_image, dict):
                        base64_image_data = first_image.get("base64") or first_image.get("image") or first_image.get("data")
                    else:
                        base64_image_data = first_image
                elif isinstance(base64_image_data, dict):
                    base64_image_data = base64_image_data.get("base64") or base64_image_data.get("image") or base64_image_data.get("data")
                if not base64_image_data:
                    raise ValueError("Fallback Nova Canvas response did not include an image")
                generated_image_data = base64.b64decode(base64_image_data)
                selected_prompt = fallback_prompt + " (fallback generation)"
                
            except Exception as fallback_error:
                print(f"[ERROR] Fallback generation also failed: {fallback_error}")
                # 모든 생성 실패 시 원본 이미지 사용
                generated_image_data = original_image_data
                selected_prompt = "Original uploaded image (AI analysis and generation failed)"

        # 4. sp-complete-bucket으로 생성된 이미지 저장
        s3.put_object(
            Bucket='sp-complete-bucket',
            Key=key,
            Body=generated_image_data,
            ContentType='image/png',
            Metadata={
                'ai-prompt': _safe_metadata_value(selected_prompt),
                'generation-type': 'nova-canvas-v1',
                'analysis-method': 'nova-pro-vision-analysis'
            }
        )
        print(f"[SUCCESS] AI generated image saved to sp-complete-bucket/{key}")

        # 5. 성공적으로 복사되면 원본 파일 삭제
        # try:
        #     s3.delete_object(Bucket=bucket, Key=key)
        #     print(f"[SUCCESS] Original file deleted from {bucket}/{key}")
        # except Exception as delete_error:
        #     print(f"[WARNING] Failed to delete original file {bucket}/{key}: {delete_error}")

        return _success(200, {
            "message": "AI image generated and saved successfully",
            "prompt": selected_prompt,
            "reason": "업로드된 이미지를 Nova Pro가 분석한 뒤 Nova Canvas로 고품질 연관 이미지를 생성했습니다"
        })

    except Exception as e:
        print("Error processing file:", e)
        return _error(500, str(e))
