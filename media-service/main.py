from fastapi import FastAPI, HTTPException, Request, Response, APIRouter
from metrics import metrics_router, UPLOAD_ISSUED_TOTAL, UPLOAD_CONFIRM_TOTAL, UPLOAD_CONFIRM_FAILED_TOTAL, PRESIGN_GET_TOTAL, PRESIGN_PUT_TOTAL, PROCESSING_LATENCY_SECONDS
from logging import setup_logging
import structlog
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from config import settings
import uuid
import time

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel, Field, root_validator
from typing import Optional, Literal
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

setup_logging()
logger = structlog.get_logger()

# Boto3 client
s3_client = boto3.client(
    's3',
    endpoint_url=settings.S3_ENDPOINT_URL,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
    config=Config(signature_version='s3v4')
)

app = FastAPI(title="Media Service")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

FastAPIInstrumentor.instrument_app(app)

app.include_router(metrics_router)

class UploadRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    visibility: Literal['public', 'private'] = 'private'

class UploadResponse(BaseModel):
    upload_id: str
    presigned_url: str
    expires_in: int

class ConfirmRequest(BaseModel):
    upload_id: str

class DownloadSignRequest(BaseModel):
    media_id: str
    ttl_seconds: int = Field(default=3600, le=86400, description="TTL must be less than or equal to 86400 seconds (24h)")

class DownloadSignResponse(BaseModel):
    presigned_url: str

# In-memory mock DB
db_pending_uploads = {}
db_media = {}

@app.post("/upload/request", response_model=UploadResponse)
@limiter.limit("10/minute")
async def request_upload(request: Request, body: UploadRequest):
    """UC-MED-001: Request Upload"""
    upload_id = str(uuid.uuid4())
    storage_key = f"{body.visibility}/{upload_id}/{body.filename}"

    try:
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': settings.S3_BUCKET_NAME, 'Key': storage_key, 'ContentType': body.content_type},
            ExpiresIn=3600
        )
        PRESIGN_PUT_TOTAL.inc()
        UPLOAD_ISSUED_TOTAL.inc()

        logger.info("Upload requested", upload_id=upload_id, storage_key=storage_key, presigned_url=presigned_url)

        # Save pending state somewhere (e.g., Redis, DB). Mocked here.
        db_pending_uploads[upload_id] = storage_key

        return {"upload_id": upload_id, "presigned_url": presigned_url, "expires_in": 3600}
    except Exception as e:
        logger.error("Error generating presigned url", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/upload/confirm")
@limiter.limit("10/minute")
async def confirm_upload(request: Request, body: ConfirmRequest):
    """UC-MED-002: Confirm Upload"""
    upload_id = body.upload_id
    storage_key = db_pending_uploads.get(upload_id)
    if not storage_key:
        raise HTTPException(status_code=404, detail="Upload request not found")

    try:
        # head_object checks if it exists and matches size
        s3_client.head_object(Bucket=settings.S3_BUCKET_NAME, Key=storage_key)

        start_time = time.time()
        # Publish event to queue (RabbitMQ/Kafka) for processing
        # Mocking background processing time for latencies
        time.sleep(0.05)
        PROCESSING_LATENCY_SECONDS.observe(time.time() - start_time)

        # Move from pending to active media
        db_media[upload_id] = storage_key
        del db_pending_uploads[upload_id]

        UPLOAD_CONFIRM_TOTAL.inc()
        logger.info("Upload confirmed", upload_id=upload_id)

        return {"status": "ok", "message": "Upload confirmed, processing started"}
    except ClientError as e:
        UPLOAD_CONFIRM_FAILED_TOTAL.inc()
        if e.response['Error']['Code'] == '404':
             logger.error("Upload confirmation failed, object not found", upload_id=upload_id)
             raise HTTPException(status_code=400, detail="Object not found or size mismatch")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/download/sign", response_model=DownloadSignResponse)
@limiter.limit("50/minute")
async def sign_download(request: Request, body: DownloadSignRequest):
    """UC-MED-003: Sign Download"""
    storage_key = db_media.get(body.media_id)
    if not storage_key:
        raise HTTPException(status_code=404, detail="Media not found")

    try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.S3_BUCKET_NAME, 'Key': storage_key},
            ExpiresIn=body.ttl_seconds
        )
        PRESIGN_GET_TOTAL.inc()
        logger.info("Download URL signed", media_id=body.media_id, presigned_url=presigned_url)
        return {"presigned_url": presigned_url}
    except Exception as e:
        logger.error("Error signing download", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/media/{media_id}")
@limiter.limit("5/minute")
async def delete_media(request: Request, media_id: str):
    """UC-MED-004: Delete Media"""
    storage_key = db_media.get(media_id)
    if not storage_key:
         raise HTTPException(status_code=404, detail="Media not found")

    try:
         s3_client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=storage_key)
         del db_media[media_id]
         logger.info("Media deleted", media_id=media_id)
         return {"status": "ok", "message": "Media deleted"}
    except Exception as e:
         logger.error("Error deleting media", error=str(e))
         raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
