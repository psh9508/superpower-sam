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
        
        # 3. WebSocket으로 완료 메시지 전송
        message = {
            "type": "image_complete",
            "message": "이미지 처리가 완료되었습니다.",
            "fileName": key
        }
        
        try:
            apigateway.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(message)
            )
            print(f"[SUCCESS] WebSocket message sent to {connection_id}")
            
            # 4. 성공적으로 WebSocket 메시지를 보냈으면 sp-complete-bucket의 파일 삭제
            try:
                s3.delete_object(Bucket=bucket, Key=key)
                print(f"[SUCCESS] Complete file deleted from {bucket}/{key}")
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
