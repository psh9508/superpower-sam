import boto3
import time
import random
import urllib.parse
import json
import base64

s3 = boto3.client('s3', region_name='ap-northeast-2')
bedrock_nova = boto3.client("bedrock-runtime", region_name="us-east-1")
bedrock_canvas = boto3.client("bedrock-runtime", region_name="us-east-1")

def lambda_handler(event, context):
    # return {
    #         "statusCode": 200,
    #         "body": json.dumps({
    #             "message": "AI image generated and saved successfully",
    #             "reason": "업로드된 이미지를 Nova Pro가 분석한 뒤 Nova Canvas로 고품질 연관 이미지를 생성했습니다"
    #         })
    #     }

    try:
        # 1. EventBridge 이벤트에서 버킷 이름과 객체 키 추출
        bucket = event['detail']['bucket']['name']
        key = urllib.parse.unquote_plus(event['detail']['object']['key'])
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
                                "text": "성장형 게임에서 사용할 아기 펫 이미지를 생성하려고해 이미지 생성에 사용할 프롬프트용 이미지의 디테일을 설명해줘"
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
            print(f"[SUCCESS] Image analyzed. Generated prompt: {analyzed_prompt}")
            
            # 2단계: 분석 결과를 바탕으로 Nova Canvas로 연관 이미지 생성
            canvas_request = {
                "taskType": "TEXT_IMAGE",
                "textToImageParams": {
                    "text": analyzed_prompt
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
                body=canvas_request
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
            
            selected_prompt = analyzed_prompt
                
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
                        "text": fallback_prompt
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
                'ai-prompt': selected_prompt,
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

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "AI image generated and saved successfully",
                "prompt": selected_prompt,
                "reason": "업로드된 이미지를 Nova Pro가 분석한 뒤 Nova Canvas로 고품질 연관 이미지를 생성했습니다"
            })
        }

    except Exception as e:
        print("Error processing file:", e)
        return {
            "statusCode": 500,
            "body": f'{{"message": "{str(e)}"}}'
        }
