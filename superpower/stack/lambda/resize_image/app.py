import boto3
import os
from io import BytesIO
from PIL import Image
import urllib.parse

s3 = boto3.client('s3', region_name='ap-northeast-2')
BUCKET_NAME = os.environ['BUCKET_NAME']

def lambda_handler(event, context):
    try:
        # 1. EventBridge 이벤트에서 버킷 이름과 객체 키 추출
        bucket = event['detail']['bucket']['name']
        key = urllib.parse.unquote_plus(event['detail']['object']['key'])
        print(f"Processing file: s3://{bucket}/{key}")

        # 2. S3에서 파일 가져오기
        response = s3.get_object(Bucket=bucket, Key=key)
        body = response['Body'].read()
        content_type = response['ContentType']
        if not body or not content_type:
            raise Exception("S3 object body or content type missing")

        # 3. 파일이 이미지인지 확인
        try:
            img = Image.open(BytesIO(body))
            img.verify()  # 이미지 유효성 체크
        except Exception:
            print("Not an image, skipping")
            return {
                "statusCode": 200,
                "body": '{"message": "Not an image, skipped."}'
            }

        # 4. 이미지 다시 열기 (verify() 후에는 reopen 필요)
        img = Image.open(BytesIO(body))
        width, height = img.size

        # 5. 300x300보다 작은 경우 그대로 복사
        if width <= 300 and height <= 300:
            print("Image smaller than or equal to 300x300, skipping resize.")
            upload_to_resized_bucket(key, body, content_type)
            return {
                "statusCode": 200,
                "body": '{"message": "Image copied without resizing."}'
            }

        # 6. 300x300 이상일 때 리사이즈
        img.thumbnail((300, 300))  # 비율 유지하며 최대 300x300
        buffer = BytesIO()
        img.save(buffer, format=img.format)
        buffer.seek(0)

        # 7. 리사이즈된 이미지 S3 업로드
        upload_to_resized_bucket(key, buffer.read(), content_type)
        print(f"Resized image uploaded to {BUCKET_NAME}/{key}")

        return {
            "statusCode": 200,
            "body": '{"message": "Image resized and uploaded successfully."}'
        }

    except Exception as e:
        print("Error processing image:", e)
        return {
            "statusCode": 500,
            "body": f'{{"message": "{str(e)}"}}'
        }

def upload_to_resized_bucket(key, data, content_type):
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=content_type
    )
