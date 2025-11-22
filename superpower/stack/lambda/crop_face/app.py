import boto3
import json
import urllib.parse
import os
from PIL import Image, ImageDraw
import io

s3 = boto3.client('s3', region_name='ap-northeast-2')
rekognition = boto3.client('rekognition', region_name='ap-northeast-2')

def lambda_handler(event, context):
    try:
        # 1. EventBridge 이벤트에서 버킷 이름과 객체 키 추출
        bucket = event['detail']['bucket']['name']
        key = urllib.parse.unquote_plus(event['detail']['object']['key'])
        print(f"Processing file: s3://{bucket}/{key}")
        
        # 2. 파일 이름에서 connectionId 추출 (파일명이 connectionId.확장자 형태)
        connection_id = key.split('.')[0]
        print(f"Extracted connectionId: {connection_id}")
        
        # 3. S3에서 이미지 파일 다운로드
        response = s3.get_object(Bucket=bucket, Key=key)
        image_data = response['Body'].read()
        
        # 4. PIL Image로 변환
        image = Image.open(io.BytesIO(image_data))
        image_width, image_height = image.size
        print(f"[INFO] Image loaded: {image_width}x{image_height}")
        
        # 5. AWS Rekognition으로 얼굴 탐지
        try:
            # Rekognition으로 얼굴 탐지
            response = rekognition.detect_faces(
                Image={'Bytes': image_data},
                Attributes=['DEFAULT']
            )
            
            face_details = response['FaceDetails']
            print(f"[SUCCESS] Detected {len(face_details)} faces using AWS Rekognition")
            
        except Exception as detection_error:
            print(f"[ERROR] Face detection failed: {detection_error}")
            face_details = []
        
        # 6. 탐지된 얼굴들 처리
        face_count = 0
        uploaded_faces = []
        
        for face_detail in face_details:
            face_count += 1
            
            # Rekognition 바운딩 박스는 비율로 반환됨
            bbox = face_detail['BoundingBox']
            
            # 실제 픽셀 좌표로 변환
            left = int(bbox['Left'] * image_width)
            top = int(bbox['Top'] * image_height)
            width = int(bbox['Width'] * image_width)
            height = int(bbox['Height'] * image_height)
            
            # 바운딩 박스 좌표 (여유 공간 추가)
            margin = int(min(width, height) * 0.1)  # 10% 여유
            x1_crop = max(0, left - margin)
            y1_crop = max(0, top - margin)
            x2_crop = min(image_width, left + width + margin)
            y2_crop = min(image_height, top + height + margin)
            
            # 얼굴 영역 크롭
            face_image = image.crop((x1_crop, y1_crop, x2_crop, y2_crop))
            
            confidence = face_detail['Confidence']
            
            # 이미지를 바이트로 변환
            img_buffer = io.BytesIO()
            face_image.save(img_buffer, format='JPEG', quality=90)
            img_buffer.seek(0)
            
            # S3에 업로드 (connectionId 폴더 안에 번호순으로)
            face_key = f"{connection_id}/{face_count}.jpg"
            
            s3.put_object(
                Bucket='sp-croped-faces-bucket',
                Key=face_key,
                Body=img_buffer.getvalue(),
                ContentType='image/jpeg',
                Metadata={
                    'original-file': key,
                    'connection-id': connection_id,
                    'face-number': str(face_count),
                    'detection-method': 'aws-rekognition',
                    'confidence': str(confidence),
                    'bbox': f"{x1_crop},{y1_crop},{x2_crop},{y2_crop}"
                }
            )
            
            uploaded_faces.append({
                'face_number': face_count,
                'detection_method': 'aws-rekognition',
                'confidence': confidence,
                'bbox': [x1_crop, y1_crop, x2_crop, y2_crop],
                's3_key': face_key
            })
            
            print(f"[SUCCESS] Face {face_count} uploaded: s3://sp-croped-faces-bucket/{face_key}")
        
        # 7. 처리 결과 로깅
        if face_count == 0:
            print("[INFO] No faces detected in the image")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "No faces detected with AWS Rekognition",
                    "connection_id": connection_id,
                    "faces_found": 0,
                    "faces": []
                })
            }
        else:
            print(f"[SUCCESS] {face_count} faces detected and cropped using AWS Rekognition")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": f"Successfully detected and cropped {face_count} faces using AWS Rekognition",
                    "connection_id": connection_id,
                    "faces_found": face_count,
                    "detection_method": "aws-rekognition",
                    "faces": uploaded_faces
                })
            }
        
    except Exception as e:
        print(f"[ERROR] Face cropping failed: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": f"Face cropping failed: {str(e)}",
                "connection_id": connection_id if 'connection_id' in locals() else 'unknown'
            })
        }