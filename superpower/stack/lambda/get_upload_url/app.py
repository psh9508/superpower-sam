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
    # 쿼리 파라미터에서 값 추출
    query_params = event.get('queryStringParameters') or {}
    file_name = query_params.get('fileName')
    key = query_params.get('key') or file_name
    content_type = query_params.get("contentType")  # ← 프런트와 동일하게 받기

    # content_type 없으면 기본값을 주되, 프런트도 그 값으로 업로드해야 합니다.
    if not content_type:
        content_type = "image/jpeg"  # 혹은 None으로 두고 서명에서 제외
    
    if not key:
        return {
            'statusCode': 400,
            'headers': cors_headers,
            'body': json.dumps({'error': 'fileName 또는 key 파라미터가 필요합니다'})
        }
    
    try:
        # upload용 presigned URL 생성 (10분 = 600초)
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': key,
                'ContentType': content_type
            },
            ExpiresIn=60
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
