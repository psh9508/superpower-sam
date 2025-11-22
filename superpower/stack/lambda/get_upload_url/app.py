import json
import os
import boto3
from botocore.exceptions import ClientError

BUCKET_NAME = os.environ['BUCKET_NAME']

cors_headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS"
}

# boto3 S3 클라이언트 생성
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    # presigned URL 발급할 객체 키
    object_key = event.get('object_key', 'example.txt')  # 기본값 example.txt
    
    try:
        # presigned URL 생성 (1분 = 60초)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': object_key
            },
            ExpiresIn=60  # URL 만료 시간 (초)
        )
        
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({'presigned_url': presigned_url})
        }
    
    except ClientError as e:
        print(e)
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }
