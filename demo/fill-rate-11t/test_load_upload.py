"""Call Spring /api/load/upload exactly like the driver app."""
import json
import os
import urllib.request


def post_multipart(url: str, path: str, truck_id: str = "7") -> dict:
    boundary = "----MoveAiLoadBoundary"
    filename = os.path.basename(path)
    with open(path, "rb") as f:
        raw = f.read()
    parts = []
    for name, value in (("truckId", truck_id),):
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    parts.append(b"Content-Type: image/png\r\n\r\n")
    parts.append(raw)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def main():
    path = "/tmp/fill_50pct.png"
    # via nginx like browser
    for label, url in [
        ("nginx", "http://mvp-moveai-nginx/api/load/upload"),
        ("spring", "http://mvp-moveai-backend-spring:8080/api/load/upload"),
    ]:
        try:
            r = post_multipart(url, path)
            print(
                json.dumps(
                    {
                        "via": label,
                        "occupiedVolumePercent": r.get("occupiedVolumePercent"),
                        "remainingVolumePercent": r.get("remainingVolumePercent"),
                        "engine": r.get("engine"),
                        "pipeline": r.get("pipeline"),
                        "logs_tail": (r.get("logs") or [])[-8:],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except Exception as e:
            print(json.dumps({"via": label, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
