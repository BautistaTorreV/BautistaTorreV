import pytest
import requests
import time

BASE_URL = "http://localhost:8000"

def wait_for_service():
    for _ in range(15):
        try:
            res = requests.get(f"{BASE_URL}/docs")
            if res.status_code == 200:
                return True
        except:
            pass
        time.sleep(2)
    return False

def test_full_media_flow():
    # Only run if service is available (for local testing without docker-compose)
    if not wait_for_service():
        pytest.skip("Service not available")

    # 1. Request Upload -> Presign
    req_payload = {
        "filename": "test.mp4",
        "content_type": "video/mp4",
        "size_bytes": 1024,
        "visibility": "private"
    }

    res = requests.post(f"{BASE_URL}/upload/request", json=req_payload)
    assert res.status_code == 200
    data = res.json()
    assert "upload_id" in data
    assert "presigned_url" in data

    upload_id = data["upload_id"]
    presigned_url = data["presigned_url"]

    # Simulate putting object into MinIO (mocked upload)
    put_res = requests.put(presigned_url, data=b"test_content", headers={"Content-Type": "video/mp4"})
    assert put_res.status_code == 200

    # 2. Confirm Upload
    confirm_payload = {"upload_id": upload_id}
    res = requests.post(f"{BASE_URL}/upload/confirm", json=confirm_payload)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # 3. Sign Download
    sign_payload = {"media_id": upload_id, "ttl_seconds": 3600}
    res = requests.post(f"{BASE_URL}/download/sign", json=sign_payload)
    assert res.status_code == 200
    sign_data = res.json()
    assert "presigned_url" in sign_data
    download_url = sign_data["presigned_url"]

    # Test downloading
    dl_res = requests.get(download_url)
    assert dl_res.status_code == 200
    assert dl_res.content == b"test_content"

    # 4. Delete
    res = requests.delete(f"{BASE_URL}/media/{upload_id}")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # 5. Sign Download after delete should fail with 404
    res_after_delete = requests.post(f"{BASE_URL}/download/sign", json=sign_payload)
    assert res_after_delete.status_code == 404
    assert res_after_delete.json()["detail"] == "Media not found"
