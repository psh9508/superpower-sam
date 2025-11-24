import boto3
import json
import urllib.parse
import os
from PIL import Image
import io

s3 = boto3.client('s3', region_name='ap-northeast-2')
rekognition = boto3.client('rekognition', region_name='ap-northeast-2')

cors_headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS"
}


def _extract_bucket_and_key(event):
    # EventBridge (S3 -> EventBridge)
    detail = event.get('detail')
    if detail:
        bucket = detail['bucket']['name']
        key = urllib.parse.unquote_plus(detail['object']['key'])
        return bucket, key

    # Direct S3 notification
    records = event.get('Records')
    if records:
        record = records[0]
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        return bucket, key

    # Manual/test invoke payloads
    if 'bucket' in event and 'key' in event:
        return event['bucket'], urllib.parse.unquote_plus(event['key'])

    raise KeyError("Event does not contain S3 bucket/key information")


def _extract_connection_id(key: str) -> str:
    parts = key.split('/')
    if parts and parts[0]:
        return parts[0]
    filename = os.path.basename(key)
    return filename.split('.')[0]


def _list_objects(bucket: str, prefix: str):
    keys = []
    continuation_token = None

    while True:
        params = {'Bucket': bucket, 'Prefix': prefix}
        if continuation_token:
            params['ContinuationToken'] = continuation_token

        response = s3.list_objects_v2(**params)
        contents = response.get('Contents', [])
        for obj in contents:
            obj_key = obj['Key']
            if obj_key.endswith('/'):
                continue
            keys.append(obj_key)

        if not response.get('IsTruncated'):
            break

        continuation_token = response.get('NextContinuationToken')

    return keys


def _crop_faces_from_image(bucket: str, key: str, connection_id: str, start_index: int = 0):
    response = s3.get_object(Bucket=bucket, Key=key)
    image_data = response['Body'].read()

    image = Image.open(io.BytesIO(image_data))
    image_width, image_height = image.size
    print(f"[INFO] Image loaded: {image_width}x{image_height} from {key}")

    try:
        detection_response = rekognition.detect_faces(
            Image={'Bytes': image_data},
            Attributes=['DEFAULT']
        )
        face_details = detection_response['FaceDetails']
        print(f"[SUCCESS] Detected {len(face_details)} faces in {key} using AWS Rekognition")
    except Exception as detection_error:
        print(f"[ERROR] Face detection failed for {key}: {detection_error}")
        face_details = []

    face_index = start_index
    uploaded_faces = []

    for face_detail in face_details:
        face_index += 1

        bbox = face_detail['BoundingBox']
        left = int(bbox['Left'] * image_width)
        top = int(bbox['Top'] * image_height)
        width = int(bbox['Width'] * image_width)
        height = int(bbox['Height'] * image_height)

        margin = int(min(width, height) * 0.1)
        x1_crop = max(0, left - margin)
        y1_crop = max(0, top - margin)
        x2_crop = min(image_width, left + width + margin)
        y2_crop = min(image_height, top + height + margin)

        face_image = image.crop((x1_crop, y1_crop, x2_crop, y2_crop))
        confidence = face_detail['Confidence']

        img_buffer = io.BytesIO()
        face_image.save(img_buffer, format='JPEG', quality=90)
        img_buffer.seek(0)

        # 요청: connectionId/face_count.jpg 형태로만 저장
        face_key = f"{connection_id}/{face_index}.jpg"

        s3.put_object(
            Bucket='sp-croped-faces-bucket',
            Key=face_key,
            Body=img_buffer.getvalue(),
            ContentType='image/jpeg',
            Metadata={
                'original-file': key,
                'connection-id': connection_id,
                'face-number': str(face_index),
                'detection-method': 'aws-rekognition',
                'confidence': str(confidence),
                'bbox': f"{x1_crop},{y1_crop},{x2_crop},{y2_crop}"
            }
        )

        uploaded_faces.append({
            'face_number': face_index,
            'detection_method': 'aws-rekognition',
            'confidence': confidence,
            'bbox': [x1_crop, y1_crop, x2_crop, y2_crop],
            's3_key': face_key,
            'source_image': key
        })

        print(f"[SUCCESS] Face {face_index} from {key} uploaded: s3://sp-croped-faces-bucket/{face_key}")

    return {
        'source_key': key,
        'faces_found': face_index - start_index,
        'faces': uploaded_faces,
        'last_index': face_index
    }


def lambda_handler(event, context):
    try:
        bucket, key = _extract_bucket_and_key(event)
        print(f"Processing file: s3://{bucket}/{key}")

        connection_id = _extract_connection_id(key)
        prefix = f"{connection_id}/"
        print(f"Extracted connectionId: {connection_id}. Listing all objects under prefix {prefix}")
        object_keys = _list_objects(bucket, prefix)

        if not object_keys:
            print(f"[INFO] No objects found under {prefix}")
            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps({
                    "message": "No images found for connectionId",
                    "connection_id": connection_id,
                    "faces_found": 0,
                    "faces": []
                })
            }

        total_faces = 0
        processed_results = []

        for object_key in object_keys:
            try:
                result = _crop_faces_from_image(bucket, object_key, connection_id, start_index=total_faces)
                processed_results.append(result)
                total_faces = result['last_index']
            except Exception as image_error:
                print(f"[ERROR] Failed processing {object_key}: {image_error}")
                processed_results.append({
                    'source_key': object_key,
                    'faces_found': 0,
                    'faces': [],
                    'error': str(image_error)
                })

        if total_faces == 0:
            print(f"[INFO] No faces detected for any images under {prefix}")
        else:
            print(f"[SUCCESS] {total_faces} faces detected and cropped from {len(object_keys)} images under {prefix}")

        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": json.dumps({
                "message": "Face cropping completed",
                "connection_id": connection_id,
                "faces_found": total_faces,
                "detection_method": "aws-rekognition",
                "results": processed_results
            })
        }

    except Exception as e:
        print(f"[ERROR] Face cropping failed: {str(e)}")
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({
                "message": f"Face cropping failed: {str(e)}",
                "connection_id": connection_id if 'connection_id' in locals() else 'unknown'
            })
        }
