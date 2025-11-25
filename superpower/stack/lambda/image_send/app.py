import boto3
import os
import time
import random
import urllib.parse
import json
import base64

s3 = boto3.client('s3', region_name='ap-northeast-2')
bedrock_nova = boto3.client("bedrock-runtime", region_name="us-east-1")
bedrock_sd = boto3.client("bedrock-runtime", region_name="us-west-2")

def lambda_handler(event, context):
     return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "AI image generated and saved successfully",
                # "prompt": selected_prompt,
                # "reason": "업로드된 이미지를 Nova Pro가 분석하여 Stable Diffusion 3.5 Large로 고품질 연관 이미지를 생성했습니다"
            })
    }
    # try:
    #     # 1. EventBridge 이벤트에서 버킷 이름과 객체 키 추출
    #     bucket = event['detail']['bucket']['name']
    #     key = urllib.parse.unquote_plus(event['detail']['object']['key'])
    #     print(f"Processing file: s3://{bucket}/{key}")

    #     # 2. 업로드된 이미지 가져와서 분석
    #     print(f"Analyzing uploaded image and generating related AI image...")
        
    #     # S3에서 업로드된 이미지 가져오기
    #     response = s3.get_object(Bucket=bucket, Key=key)
    #     original_image_data = response['Body'].read()
    #     original_image_base64 = base64.b64encode(original_image_data).decode('utf-8')
        
    #     # 업로드된 이미지 분석 후 연관 이미지 생성
    #     try:
    #         start_time = time.time()
            
    #         # 1단계: Nova Pro를 사용해 이미지 분석 (us-east-1에서 호출)
    #         analysis_request = {
    #             "messages": [
    #                 {
    #                     "role": "user",
    #                     "content": [
    #                         {
    #                             "image": {
    #                                 "format": "jpeg",
    #                                 "source": {
    #                                     "bytes": original_image_base64
    #                                 }
    #                             }
    #                         },
    #                         {
    #                             "text": "이 사람 얼굴을 어떤 동물과 닮았는지 간단히 설명해 주세요. 그리고 그 동물을 창의적이고 예술적인 방식으로 묘사하는 프롬프트를 만들어 주세요."
    #                         }
    #                     ]
    #                 }
    #             ]
    #         }
            
    #         # Nova Pro로 이미지 분석
    #         analysis_response = bedrock_nova.invoke_model(
    #             modelId="amazon.nova-pro-v1:0",
    #             contentType="application/json",
    #             accept="application/json",
    #             body=json.dumps(analysis_request)
    #         )
            
    #         analysis_result = json.loads(analysis_response["body"].read())
    #         analyzed_prompt = analysis_result["output"]["message"]["content"][0]["text"].strip()
    #         print(f"[SUCCESS] Image analyzed. Generated prompt: {analyzed_prompt}")
            
    #         # 2단계: 분석 결과를 바탕으로 Stable Diffusion 3.5 Large로 연관 이미지 생성
    #         # SD 3.5 text-to-image request (cfg/steps/width/height are not supported)
    #         sd_request = {
    #             "prompt": analyzed_prompt,
    #             "mode": "text-to-image",
    #             "output_format": "png",
    #             "aspect_ratio": "1:1",
    #         }
            
    #         # SD 모델은 us-west-2에서 제공됨
    #         sd_response = bedrock_sd.invoke_model(
    #             modelId="stability.sd3-5-large-v1:0",
    #             contentType="application/json",
    #             accept="application/json",
    #             body=json.dumps(sd_request)
    #         )
            
    #         sd_result = json.loads(sd_response["body"].read())
    #         base64_image_data = sd_result.get("image") or (sd_result.get("images") or [None])[0]
    #         if not base64_image_data:
    #             raise ValueError("Stable Diffusion response did not include an image")
    #         generated_image_data = base64.b64decode(base64_image_data)
            
    #         generation_time = time.time() - start_time
    #         print(f"[SUCCESS] Related AI image generated in {generation_time:.2f} seconds")
            
    #         selected_prompt = analyzed_prompt
                
    #     except Exception as bedrock_error:
    #         print(f"[WARNING] Bedrock analysis/generation failed: {bedrock_error}")
    #         # 분석 실패 시 원본 파일 사용하고 기본 프롬프트로 새 이미지 생성
    #         fallback_prompts = [
    #             "A creative artistic interpretation with vibrant colors",
    #             "An abstract artistic version with modern style",
    #             "A fantasy reimagining with magical elements",
    #             "A minimalist artistic interpretation",
    #             "A surreal artistic transformation"
    #         ]
            
    #         try:
    #             fallback_prompt = random.choice(fallback_prompts)
    #             fallback_request = {
    #                 "prompt": fallback_prompt,
    #                 "mode": "text-to-image",
    #                 "output_format": "png",
    #                 "aspect_ratio": "1:1",
    #             }
                
    #             fallback_response = bedrock_sd.invoke_model(
    #                 modelId="stability.sd3-5-large-v1:0",
    #                 contentType="application/json",
    #                 accept="application/json",
    #                 body=json.dumps(fallback_request)
    #             )
                
    #             fallback_result = json.loads(fallback_response["body"].read())
    #             base64_image_data = fallback_result.get("image") or (fallback_result.get("images") or [None])[0]
    #             if not base64_image_data:
    #                 raise ValueError("Fallback Stable Diffusion response did not include an image")
    #             generated_image_data = base64.b64decode(base64_image_data)
    #             selected_prompt = fallback_prompt + " (fallback generation)"
                
    #         except Exception as fallback_error:
    #             print(f"[ERROR] Fallback generation also failed: {fallback_error}")
    #             # 모든 생성 실패 시 원본 이미지 사용
    #             generated_image_data = original_image_data
    #             selected_prompt = "Original uploaded image (AI analysis and generation failed)"

    #     # 4. sp-complete-bucket으로 생성된 이미지 저장
    #     s3.put_object(
    #         Bucket='sp-complete-bucket',
    #         Key=key,
    #         Body=generated_image_data,
    #         ContentType='image/png',
    #         Metadata={
    #             'ai-prompt': selected_prompt,
    #             'generation-type': 'stable-diffusion-3.5-large',
    #             'analysis-method': 'nova-pro-vision-analysis'
    #         }
    #     )
    #     print(f"[SUCCESS] AI generated image saved to sp-complete-bucket/{key}")

    #     # 5. 성공적으로 복사되면 원본 파일 삭제
    #     # try:
    #     #     s3.delete_object(Bucket=bucket, Key=key)
    #     #     print(f"[SUCCESS] Original file deleted from {bucket}/{key}")
    #     # except Exception as delete_error:
    #     #     print(f"[WARNING] Failed to delete original file {bucket}/{key}: {delete_error}")

    #     return {
    #         "statusCode": 200,
    #         "body": json.dumps({
    #             "message": "AI image generated and saved successfully",
    #             "prompt": selected_prompt,
    #             "reason": "업로드된 이미지를 Nova Pro가 분석하여 Stable Diffusion 3.5 Large로 고품질 연관 이미지를 생성했습니다"
    #         })
    #     }

    # except Exception as e:
    #     print("Error processing file:", e)
    #     return {
    #         "statusCode": 500,
    #         "body": f'{{"message": "{str(e)}"}}'
    #     }
