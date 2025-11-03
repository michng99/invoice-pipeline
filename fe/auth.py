import os
import requests as req

def get_id_token(audience: str) -> str | None:
    # Cloud Run: metadata server
    try:
        metadata_url = (
            "http://metadata/computeMetadata/v1/instance/service-accounts/default/identity?"
            f"audience={audience}"
        )
        headers = {"Metadata-Flavor": "Google"}
        r = req.get(metadata_url, headers=headers, timeout=3)
        if r.ok and r.text:
            return r.text
    except Exception:
        pass

    # Local fallback: export ID_TOKEN
    return os.getenv("ID_TOKEN")
