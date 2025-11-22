import boto3
import os
import time
import random
import urllib.parse

s3 = boto3.client('s3', region_name='ap-northeast-2')

def lambda_handler(event, context):
    try:
        # 1. EventBridge 이벤트에서 버킷 이름과 객체 키 추출
        bucket = event['detail']['bucket']['name']
        key = urllib.parse.unquote_plus(event['detail']['object']['key'])
        print(f"Processing file: s3://{bucket}/{key}")

        # 2. 랜덤 3-6초 대기
        wait_time = random.uniform(3, 6)
        print(f"Waiting {wait_time:.2f} seconds...")
        time.sleep(wait_time)

        # 3. S3에서 파일 가져오기
        response = s3.get_object(Bucket=bucket, Key=key)
        body = response['Body'].read()
        content_type = response['ContentType']
        if not body or not content_type:
            raise Exception("S3 object body or content type missing")

        # 4. sp-complete-bucket으로 파일을 그대로 복사
        s3.put_object(
            Bucket='sp-complete-bucket',
            Key=key,
            Body=body,
            ContentType=content_type
        )
        print(f"[SUCCESS] File copied to sp-complete-bucket/{key}")

        # 5. 성공적으로 복사되면 원본 파일 삭제
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            print(f"[SUCCESS] Original file deleted from {bucket}/{key}")
        except Exception as delete_error:
            print(f"[WARNING] Failed to delete original file {bucket}/{key}: {delete_error}")

        return {
            "statusCode": 200,
            "body": '{"message": "File copied to complete bucket and original deleted successfully."}'
        }

    except Exception as e:
        print("Error processing file:", e)
        return {
            "statusCode": 500,
            "body": f'{{"message": "{str(e)}"}}'
        }
