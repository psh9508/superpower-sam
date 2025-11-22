import boto3
import json
import urllib.parse

apigateway = boto3.client('apigatewaymanagementapi', 
                         endpoint_url='https://9ad8ivmy7e.execute-api.ap-northeast-2.amazonaws.com/dev')

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
            print(f"WebSocket message sent to {connection_id}")
            
        except apigateway.exceptions.GoneException:
            print(f"Connection {connection_id} is no longer available")
        except Exception as ws_error:
            print(f"Error sending WebSocket message: {ws_error}")

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Notification sent successfully"})
        }

    except Exception as e:
        print("Error processing notification:", e)
        return {
            "statusCode": 500,
            "body": json.dumps({"message": str(e)})
        }
