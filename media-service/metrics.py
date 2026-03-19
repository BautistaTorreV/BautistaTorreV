from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter
from starlette.responses import Response

# Metrics Definitions
UPLOAD_ISSUED_TOTAL = Counter(
    "upload_issued_total",
    "Total number of upload requests issued"
)

UPLOAD_CONFIRM_TOTAL = Counter(
    "upload_confirm_total",
    "Total number of successfully confirmed uploads"
)

UPLOAD_CONFIRM_FAILED_TOTAL = Counter(
    "upload_confirm_failed_total",
    "Total number of failed upload confirmations"
)

PRESIGN_GET_TOTAL = Counter(
    "presign_get_total",
    "Total number of presigned GET URLs generated"
)

PRESIGN_PUT_TOTAL = Counter(
    "presign_put_total",
    "Total number of presigned PUT URLs generated"
)

PROCESSING_LATENCY_SECONDS = Histogram(
    "processing_latency_seconds",
    "Latency of media processing (if any background processing exists)"
)

metrics_router = APIRouter()

@metrics_router.get("/metrics")
def get_metrics():
    """Endpoint to expose Prometheus metrics."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
