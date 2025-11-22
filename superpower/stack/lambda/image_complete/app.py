import boto3
import json
import urllib.parse

apigateway = boto3.client('apigatewaymanagementapi', 
                         endpoint_url='https://9ad8ivmy7e.execute-api.ap-northeast-2.amazonaws.com/dev')
s3 = boto3.client('s3', region_name='ap-northeast-2')

def lambda_handler(event, context):
    try:
        # 1. EventBridge 이벤트에서 버킷 이름과 객체 키 추출
        bucket = event['detail']['bucket']['name']
        key = urllib.parse.unquote_plus(event['detail']['object']['key'])
        print(f"Processing file: s3://{bucket}/{key}")
        
        # 2. 파일 이름에서 connectionId 추출 (파일명이 connectionId.확장자 형태)
        connection_id = key.split('.')[0]
        print(f"Extracted connectionId: {connection_id}")
        
        # 3. 완료된 파일에 대한 presigned URL 생성
        try:
            presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket,
                    'Key': key
                },
                ExpiresIn=600
            )
            print(f"[SUCCESS] Generated presigned URL for {bucket}/{key}")
        except Exception as url_error:
            print(f"[ERROR] Failed to generate presigned URL: {url_error}")
            presigned_url = None
        
        # 4. WebSocket으로 완료 메시지 전송
        message = {
            "type": "image_complete",
            "message": "이미지 처리가 완료되었습니다.",
            "fileName": key,
            "downloadUrl": presigned_url
        }
        
        try:
            apigateway.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(message)
            )
            print(f"[SUCCESS] WebSocket message sent to {connection_id}")
            
            # 5. presigned URL이 생성된 경우에만 파일 삭제 (URL이 유효한 동안은 파일 유지 필요)
            # 파일 삭제는 presigned URL 만료 후 별도 스케줄러로 처리하거나
            # 사용자가 다운로드 완료를 알려주는 API를 만들어 처리하는 것이 좋음
            if presigned_url:
                print(f"[INFO] File kept for download access: {bucket}/{key}")
            else:
                # presigned URL 생성 실패 시에만 즉시 삭제
                try:
                    s3.delete_object(Bucket=bucket, Key=key)
                    print(f"[SUCCESS] Failed URL generation - file deleted from {bucket}/{key}")
                except Exception as delete_error:
                    print(f"[WARNING] Failed to delete complete file {bucket}/{key}: {delete_error}")
            
        except apigateway.exceptions.GoneException:
            print(f"[INFO] Connection {connection_id} is no longer available")
        except Exception as ws_error:
            print(f"[ERROR] Failed sending WebSocket message: {ws_error}")

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Notification sent and file cleaned up successfully"})
        }

    except Exception as e:
        print("Error processing notification:", e)
        return {
            "statusCode": 500,
            "body": json.dumps({"message": str(e)})
        }
