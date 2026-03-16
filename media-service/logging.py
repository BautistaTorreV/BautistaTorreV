import structlog
import logging
import sys
import re

def mask_presigned_url(logger, log_method, event_dict):
    """
    Processor to mask sensitive tokens in presigned URLs in the logs.
    Example: https://bucket.s3.amazonaws.com/object?AWSAccessKeyId=...&Signature=...
    """
    url_pattern = re.compile(r"(AWSAccessKeyId|Signature|X-Amz-Credential|X-Amz-Signature)=([^&\s]+)")
    for key, value in event_dict.items():
        if isinstance(value, str) and ("AWSAccessKeyId=" in value or "X-Amz-Credential=" in value):
            event_dict[key] = url_pattern.sub(r"\1=MASKED", value)
    return event_dict

def setup_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            mask_presigned_url,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

log = structlog.get_logger()
