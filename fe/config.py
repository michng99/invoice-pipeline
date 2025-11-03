import os
BACKEND_URL = os.getenv("BACKEND_URL", "https://YOUR-BACKEND-URL.a.run.app")
HEALTH_URL  = f"{BACKEND_URL}/health"
PIPELINE_URL= f"{BACKEND_URL}/pipeline/xml-to-xlsx"
