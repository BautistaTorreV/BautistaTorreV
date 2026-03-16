# Media Service

Microservicio encargado de la gestión de archivos multimedia (imágenes, audios, videos) utilizando Amazon S3 (o MinIO). Implementa la generación de URLs firmadas (Presigned URLs) tanto para subida (PUT) como para descarga (GET), asegurando que el microservicio en sí no tenga que intermediar la transferencia de los bytes pesados, descargando la red y usando directamente el ancho de banda del object storage.

## Walkthrough de la Implementación de Producción-Ready

1. **Métricas Prometheus**:
   - Agregadas las métricas básicas `upload_issued_total`, `upload_confirm_total`, `upload_confirm_failed_total` (Contadores).
   - Métricas de presigned URLs: `presign_get_total`, `presign_put_total`.
   - Histograma de latencia para procesamiento en background: `processing_latency_seconds`.
2. **Tracing OTel y Logging**:
   - Instrumentación automática con `FastAPIInstrumentor`.
   - `structlog` configurado para emitir logs en formato JSON estructurado.
   - Procesador custom `mask_presigned_url` para ocultar `AWSAccessKeyId` y `Signature` en los logs y evitar exponer credenciales o tokens.
3. **Rate Limiting**:
   - Implementado internamente en los endpoints con `SlowAPI` a modo de fallback y defensa en profundidad, idealmente debe configurarse a nivel de API Gateway.
4. **Seguridad y Validación**:
   - Uso exhaustivo de Pydantic para validar los requests (e.g. `ttl_seconds <= 86400`).
   - Los storage keys (`visibility/upload_id/filename`) se mantienen ocultos del response al cliente final, solo se le entregan las URLs firmadas y los IDs de los medios.

## Use Cases Implementados

* **UC-MED-001 (Request Upload)**: El cliente solicita subir un archivo enviando el tipo, tamaño y nombre. El backend genera una Presigned URL (PUT) y se la devuelve para que el cliente haga la subida directamente a S3/MinIO.
* **UC-MED-002 (Confirm Upload)**: Luego de subir los bytes a la URL firmada, el cliente le avisa al backend. El backend verifica (`head_object`) que el archivo exista en S3. En este punto se puede desencadenar un proceso en background (video transcoding, image resizing).
* **UC-MED-003 (Sign Download)**: El cliente solicita poder visualizar un medio. El backend valida el acceso y le devuelve una Presigned URL (GET) con un `ttl_seconds` válido.
* **UC-MED-004 (Delete Media)**: Borrado lógico y físico de un medio en S3.
* **UC-MED-005..007 (Procesamiento Background/Thumbnails/Cleanup)**: Contemplados teóricamente para delegar a RabbitMQ o Celery en caso de ser necesarios.

## Variables de Entorno

| Variable | Descripción | Default |
| -------- | ----------- | ------- |
| `S3_ENDPOINT_URL` | URL de la API compatible S3 (AWS, MinIO) | `http://localhost:9000` |
| `S3_ACCESS_KEY` | Access Key de AWS/MinIO | `minioadmin` |
| `S3_SECRET_KEY` | Secret Key de AWS/MinIO | `minioadmin` |
| `S3_BUCKET_NAME` | Nombre del Bucket en el Object Storage | `media-bucket` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Endpoint para el collector OTel | `http://localhost:4317` |

## Instrucciones para Correr (Desarrollo y Testing E2E)

Para levantar el servicio junto con un MinIO embebido configurado para testing E2E:

```bash
docker-compose -f docker-compose.test.yml up -d
```

Para correr los tests E2E:

```bash
pip install -r requirements.txt
pytest test_e2e.py -v
```

Para detener los servicios:

```bash
docker-compose -f docker-compose.test.yml down -v
```

## Troubleshooting

- **Error: 400 Bad Request - Object not found or size mismatch (Confirm Upload)**: Asegúrate de haber realizado el request PUT (`requests.put(presigned_url)`) con el archivo completo antes de invocar a `/upload/confirm`.
- **Firma Inválida en MinIO**: Si estás corriendo detrás de un proxy o en localhost, asegúrate que la variable `S3_ENDPOINT_URL` que el Media Service usa para generar la URL sea la misma que tu cliente puede resolver desde su red (por ejemplo, si usas `http://minio:9000` internamente en Docker pero tú testeas desde `localhost`). Para desarrollo, normalmente usar `http://localhost:9000` mapeando el puerto resuelve el problema.
