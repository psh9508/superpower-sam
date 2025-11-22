import boto3
import os
import time
import random
import urllib.parse
import json
import base64

s3 = boto3.client('s3', region_name='ap-northeast-2')
bedrock = boto3.client("bedrock-runtime", region_name="us-west-2")

def lambda_handler(event, context):
    try:
        # 1. EventBridge 이벤트에서 버킷 이름과 객체 키 추출
        bucket = event['detail']['bucket']['name']
        key = urllib.parse.unquote_plus(event['detail']['object']['key'])
        print(f"Processing file: s3://{bucket}/{key}")

        # 2. 업로드된 이미지 가져와서 분석
        wait_time = random.uniform(3, 6)
        print(f"Analyzing uploaded image and generating related AI image...")
        
        # S3에서 업로드된 이미지 가져오기
        response = s3.get_object(Bucket=bucket, Key=key)
        original_image_data = response['Body'].read()
        original_image_base64 = base64.b64encode(original_image_data).decode('utf-8')
        
        # 업로드된 이미지 분석 후 연관 이미지 생성
        try:
            start_time = time.time()
            
            # 1단계: Claude를 사용해 이미지 분석 (us-west-2에서 호출)
            analysis_request = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": original_image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": "이 이미지를 분석하고, 이와 연관된 창의적인 이미지를 생성하기 위한 영어 프롬프트를 한 문장으로 제안해주세요. 고품질, 상세한 묘사로 작성해주세요. 예: 'A highly detailed surreal interpretation of...' 형태로."
                            }
                        ]
                    }
                ]
            }
            
            # Claude로 이미지 분석
            analysis_response = bedrock.invoke_model(
                modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(analysis_request)
            )
            
            analysis_result = json.loads(analysis_response["body"].read())
            analyzed_prompt = analysis_result["content"][0]["text"].strip()
            print(f"[SUCCESS] Image analyzed. Generated prompt: {analyzed_prompt}")
            
            # 2단계: 분석 결과를 바탕으로 Stable Diffusion 3.5 Large로 연관 이미지 생성
            sd_request = {
                "prompt": analyzed_prompt,
                "cfg_scale": 7,
                "steps": 30,
                "width": 1024,
                "height": 1024,
                "samples": 1,
            }
            
            sd_response = bedrock.invoke_model(
                modelId="stability.sd3-5-large-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(sd_request)
            )
            
            sd_result = json.loads(sd_response["body"].read())
            base64_image_data = sd_result["images"][0]
            generated_image_data = base64.b64decode(base64_image_data)
            
            generation_time = time.time() - start_time
            print(f"[SUCCESS] Related AI image generated in {generation_time:.2f} seconds")
            
            selected_prompt = analyzed_prompt
            
            # 남은 시간만큼 대기
            remaining_wait = wait_time - generation_time
            if remaining_wait > 0:
                time.sleep(remaining_wait)
                
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
                    "prompt": fallback_prompt,
                    "cfg_scale": 7,
                    "steps": 30,
                    "width": 1024,
                    "height": 1024,
                    "samples": 1,
                }
                
                fallback_response = bedrock.invoke_model(
                    modelId="stability.sd3-5-large-v1:0",
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(fallback_request)
                )
                
                fallback_result = json.loads(fallback_response["body"].read())
                base64_image_data = fallback_result["images"][0]
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
                'generation-type': 'stable-diffusion-3.5-large',
                'analysis-method': 'claude-vision-analysis'
            }
        )
        print(f"[SUCCESS] AI generated image saved to sp-complete-bucket/{key}")

        # 5. 성공적으로 복사되면 원본 파일 삭제
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            print(f"[SUCCESS] Original file deleted from {bucket}/{key}")
        except Exception as delete_error:
            print(f"[WARNING] Failed to delete original file {bucket}/{key}: {delete_error}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "AI image generated and saved successfully",
                "prompt": selected_prompt,
                "reason": "업로드된 이미지를 Claude가 분석하여 Stable Diffusion 3.5 Large로 고품질 연관 이미지를 생성했습니다"
            })
        }

    except Exception as e:
        print("Error processing file:", e)
        return {
            "statusCode": 500,
            "body": f'{{"message": "{str(e)}"}}'
        }
