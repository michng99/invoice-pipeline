from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.gzip import GZipMiddleware
import io, asyncio, httpx, xmltodict, pandas as pd, yaml, re
from typing import List, Optional, Dict, Any

from app.converters.flatten_batch import flatten_invoice, headers

app = FastAPI(title="XML→JSON→XLSX")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*", "localhost"])

MAX_BYTES=5*1024*1024
PRIVATE= re.compile(r"^(127\\.|10\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[0-1])\\.|localhost|169\\.254\\.169\\.254)")

@app.get("/health")
def health(): return {"ok": True}

def parse_xml(text:str)->Dict[str,Any]:
    return xmltodict.parse(text)

def load_schema(p="app/schemas/schema.yaml"):
    with open(p,"r",encoding="utf-8") as f: return yaml.safe_load(f)

@app.post("/pipeline/xml-to-xlsx")
async def pipeline(
    schema_name: str = Form("schema.yaml"),
    xml_files: Optional[List[UploadFile]] = File(None),
    xml_urls: Optional[List[str]] = Form(None),
):
    invoices=[]
    # URLs
    if xml_urls:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            tasks=[]
            for u in xml_urls:
                if not u.startswith(("http://","https://")) or PRIVATE.search(u):
                    raise HTTPException(400, "Invalid URL")
                tasks.append(client.get(u))
            res = await asyncio.gather(*tasks, return_exceptions=True)
            for r in res:
                if isinstance(r, Exception) or r.status_code!=200:
                    raise HTTPException(502, "Fetch URL failed")
                if int(r.headers.get("content-length","0"))>MAX_BYTES:
                    raise HTTPException(413,"Payload too large")
                invoices.append(parse_xml(r.text))
    # Files
    if xml_files:
        for f in xml_files:
            if not f.filename.lower().endswith(".xml"):
                raise HTTPException(400, "Only .xml allowed")
            data = await f.read()
            if len(data)>MAX_BYTES: raise HTTPException(413,"Payload too large")
            invoices.append(parse_xml(data.decode("utf-8",errors="ignore")))

    if not invoices: raise HTTPException(400,"No XML provided")

    schema = load_schema(f"app/schemas/{schema_name}")
    rows=[]
    for inv in invoices:
        rows += flatten_invoice(inv, schema)

    df = pd.DataFrame(rows, columns=headers(schema))
    buf=io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=schema["xlsx"].get("sheet_name","Data"))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="converted.xlsx"'}
    )
