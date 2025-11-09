# app/main.py
from __future__ import annotations

import io
import time
import zipfile
from typing import Dict, List, Tuple, Optional, Any
import os

import pandas as pd
import xmltodict
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

# ================== CẤU HÌNH CHUNG ==================
APP_VERSION = "v2.4-rules"
MAX_FILES = 50
MAX_FILE_SIZE = 10 * 1024 * 1024     # 10MB / file
MAX_TOTAL_SIZE = 50 * 1024 * 1024    # 50MB / request

RATE_LIMIT_WINDOW = 10               # giây
RATE_LIMIT_MAX_CALLS = 20            # mỗi IP trong 10s

# Bộ nhớ tạm cho rate-limit (per-instance)
_rate_store: Dict[str, List[float]] = {}

# ================== TIỆN ÍCH BẢO VỆ ==================
def _client_ip(request: Request, x_client_ip_hdr: Optional[str]) -> str:
    if x_client_ip_hdr:
        return x_client_ip_hdr
    if request.client:
        return request.client.host or "unknown"
    return "unknown"

def _check_rate_limit(ip: str) -> None:
    now = time.time()
    buf = _rate_store.get(ip, [])
    buf = [t for t in buf if now - t <= RATE_LIMIT_WINDOW]
    if len(buf) >= RATE_LIMIT_MAX_CALLS:
        raise HTTPException(status_code=429, detail="Too Many Requests")
    buf.append(now)
    _rate_store[ip] = buf

# (Đảm bảo bạn đã import io)
async def _validate_and_read_files(files: List[UploadFile]) -> Dict[str, bytes]:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded (form field 'files').")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=413, detail=f"Too many files (> {MAX_FILES}).")

    seen = set()
    total_size = 0
    out: Dict[str, bytes] = {}
    chunk_size = 4 * 1024 * 1024  # Đọc 4MB mỗi lần

    for uf in files:
        name = (uf.filename or "unnamed.xml").strip()
        if not name.lower().endswith(".xml"):
            raise HTTPException(status_code=415, detail=f"Invalid file type for '{name}', only .xml allowed.")
        if name in seen:
            raise HTTPException(status_code=409, detail=f"Duplicate filename: {name}")
        seen.add(name)

        file_chunks = []
        file_size = 0

        # Đọc từng chunk để kiểm tra kích thước
        while True:
            chunk = await uf.file.read(chunk_size)
            if not chunk:
                break

            file_size += len(chunk)
            total_size += len(chunk)

            if file_size > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail=f"File too large: {name} (> {MAX_FILE_SIZE} bytes)")
            if total_size > MAX_TOTAL_SIZE:
                raise HTTPException(status_code=413, detail=f"Total upload too large (> {MAX_TOTAL_SIZE} bytes)")

            file_chunks.append(chunk)

        if file_size == 0:
            raise HTTPException(status_code=400, detail=f"Empty file: {name}")

        # Nối các chunk lại thành 1 file bytes
        out[name] = b"".join(file_chunks)
        await uf.file.close()

    return out

# ================== HELPERS NGHIỆP VỤ ==================
def _ttin_to_map(ttin_container: Any) -> Dict[str, Any]:
    """
    Chuyển TTKhac.TTin (list các {TTruong,DLieu,...}) thành dict map.
    Hỗ trợ cả trường hợp 1 phần tử (dict) hoặc nhiều (list).
    """
    mp: Dict[str, Any] = {}
    if not ttin_container:
        return mp
    items = ttin_container
    if isinstance(items, dict):
        items = [items]
    for node in items:
        try:
            key = str(node.get("TTruong", "")).strip()
            val = node.get("DLieu", "")
            if key:
                mp[key] = val
        except Exception:
            continue
    return mp

def _extract_currency_and_rate(hdon: dict) -> Tuple[str, str, int, int, int, int]:
    """
    Lấy Đơn vị tiền, Tỷ giá và các decimal digits mong muốn.
    - AmountDecimalDigits: áp cho tiền (Thành tiền, VAT, Cộng tiền)
    - QuantityDecimalDigits: số lượng
    - UnitPriceDecimalDigits: đơn giá
    - ExchangRateDecimalDigits: tỷ giá
    Mặc định: Tiền 0 (VND) hoặc 2 (ngoại tệ); SL 2; Đơn giá 2; Tỷ giá 2.
    """
    dlh = hdon.get("DLHDon") or {}
    ttchung = dlh.get("TTChung") or {}
    dvtte = str(ttchung.get("DVTTe") or "")
    tgia = str(ttchung.get("TGia") or "")

    # defaults
    money_default = 0 if (dvtte.upper() == "VND" or dvtte == "") else 2
    qty_default = 2
    price_default = 2
    rate_default = 2

    # đọc TTKhac (gốc hóa đơn)
    root_ttkhac = (hdon.get("TTKhac") or {})
    root_map = _ttin_to_map(root_ttkhac.get("TTin"))

    def _to_int(s, default):
        try:
            return int(str(s).strip())
        except Exception:
            return default

    amount_digits = _to_int(root_map.get("AmountDecimalDigits"), money_default)
    qty_digits    = _to_int(root_map.get("QuantityDecimalDigits"), qty_default)
    price_digits  = _to_int(root_map.get("UnitPriceDecimalDigits"), price_default)
    rate_digits   = _to_int(root_map.get("ExchangRateDecimalDigits"), rate_default)

    return dvtte, tgia, amount_digits, qty_digits, price_digits, rate_digits

def _iter_items(hdon: dict) -> List[dict]:
    dlh = hdon.get("DLHDon") or {}
    nd = dlh.get("NDHDon") or {}
    dshhdv = nd.get("DSHHDVu") or {}
    hh = dshhdv.get("HHDVu")
    if not hh:
        return []
    if isinstance(hh, dict):
        return [hh]
    return hh

def _to_float(x) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return 0.0

def _contains_phrase(xml_text: str, needle: str) -> bool:
    return (needle in xml_text) if xml_text else False

# ================== ÁP DỤNG RULE (核心) ==================
def _xml_to_rows_with_rules(xml_bytes: bytes, source_name: str) -> List[Dict]:
    """
    Áp rule:
      - Lọc: giữ TChat != "1"
      - Thuế suất = 0.08
      - VAT = ThTien * 0.08
      - Cộng tiền = UnitPriceAfterTax * SL (fallback: ThTien + VAT)
      - Đơn vị tiền & Tỷ giá từ TTChung
      - Làm tròn theo decimal digits trong TTKhac (gốc hóa đơn)
      - Ghi chú theo cụm từ trong file
    """
    doc = xmltodict.parse(xml_bytes)
    hdon = doc.get("HDon") or {}

    # Đơn vị tiền, Tỷ giá & decimal digits
    dvtte, tgia, amount_digits, qty_digits, price_digits, rate_digits = _extract_currency_and_rate(hdon)

    # Xác định Ghi chú
    xml_text = ""
    try:
        xml_text = xml_bytes.decode("utf-8", errors="ignore")
    except Exception:
        xml_text = ""
    if _contains_phrase(xml_text, "Điều chỉnh cho hóa đơn"):
        ghichu = "Hoá đơn điều chỉnh"
    elif _contains_phrase(xml_text, "Thay thế cho hóa đơn"):
        ghichu = "Hoá đơn thay thế"
    else:
        ghichu = "Hoá đơn mới"

    items = _iter_items(hdon)
    rows: List[Dict] = []

    for it in items:
        tchat = str(it.get("TChat", "")).strip()
        if tchat == "1":
            # theo rule: loại bỏ dòng TChat=1
            continue

        # TTKhac của dòng → map để lấy UnitPriceAfterTax, DVT, v.v.
        line_map = _ttin_to_map((it.get("TTKhac") or {}).get("TTin"))

        ten_hang = it.get("THHDVu", "")
        dvt = it.get("DVTinh", "") or line_map.get("MainUnitName", "")
        sl  = _to_float(it.get("SLuong", "0"))
        dg  = _to_float(it.get("DGia", "0"))
        tht = _to_float(it.get("ThTien", "0"))
        unit_price_after_tax = _to_float(line_map.get("UnitPriceAfterTax", "0"))

        # Thuế suất & VAT
        tax_rate = 0.08
        vat_amt  = round(tht * tax_rate, amount_digits)

        # Cộng tiền (tổng đã VAT của dòng)
        if unit_price_after_tax > 0 and sl > 0:
            cong_tien = round(unit_price_after_tax * sl, amount_digits)
        else:
            cong_tien = round(tht + vat_amt, amount_digits)

        # Làm tròn các trường còn lại
        sl_out  = round(sl, qty_digits)
        dg_out  = round(dg, price_digits)
        tht_out = round(tht, amount_digits)
        tgia_out = round(_to_float(tgia), rate_digits) if tgia else ""

        row = {
            "Cờ (Tchat)": tchat,
            "Tên hàng": ten_hang,
            "ĐVT": dvt,
            "SL": sl_out,
            "Đơn giá": dg_out,
            "Thành tiền": tht_out,
            "Thuế suất": tax_rate,         # luôn 0.08
            "Tiền thuế": vat_amt,
            "Cộng tiền": cong_tien,
            "Đơn vị tiền": dvtte,
            "Tỷ giá": tgia_out,
            "Ghi chú": ghichu,
            "Nguồn (file)": source_name,
        }
        rows.append(row)

    return rows

# ================== FASTAPI APP ==================
app = FastAPI(title="Invoice Pipeline BE", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True, "version": app.version}

# trong endpoint xml_to_xlsx thêm nhận header bypass và truyền vào:
from typing import Optional  # nếu chưa import

@app.post("/pipeline/xml-to-xlsx")
async def xml_to_xlsx(
    request: Request,
    files: List[UploadFile] = File(..., description="Multipart key 'files' (multi)"),
    merge_to_one: str = Form("true"),
    x_client_ip: Optional[str] = Header(default=None, convert_underscores=False),
):
    # Bước 4: Bảo vệ Rate Limit (đã có)
    ip = _client_ip(request, x_client_ip)
    _check_rate_limit(ip)

    # Bước 3: Bảo vệ Đọc file (đã vá DoS)
    # Lưu ý: Hàm này bây giờ là async, nên phải 'await'
    filemap = await _validate_and_read_files(files)
    merge = (merge_to_one.lower() == "true")

    if merge:
        # Gộp tất cả hóa đơn thành 1 Data.xlsx
        all_rows: List[Dict] = []
        for name, data in filemap.items():
            all_rows.extend(_xml_to_rows_with_rules(data, name))
        df = pd.DataFrame(all_rows)
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="xlsxwriter") as xw:
            df.to_excel(xw, index=False, sheet_name="Data")
        headers = {"Content-Disposition": 'attachment; filename="Data.xlsx"'}
        return StreamingResponse(
            io.BytesIO(bio.getvalue()),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    else:
        # Mỗi hóa đơn một Excel, nén ZIP
        zipbio = io.BytesIO()
        with zipfile.ZipFile(zipbio, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in filemap.items():
                rows = _xml_to_rows_with_rules(data, name)
                df = pd.DataFrame(rows)
                xbio = io.BytesIO()
                with pd.ExcelWriter(xbio, engine="xlsxwriter") as xw:
                    df.to_excel(xw, index=False, sheet_name="Data")
                zf.writestr(name.rsplit(".", 1)[0] + ".xlsx", xbio.getvalue())
        headers = {"Content-Disposition": 'attachment; filename="excels.zip"'}
        return StreamingResponse(io.BytesIO(zipbio.getvalue()), media_type="application/zip", headers=headers)

# ================ HANDLERS CHUẨN HÓA LỖI ================
@app.exception_handler(HTTPException)
async def http_exc_handler(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

# ================ GỢI Ý CHẠY LOCAL =================
# uvicorn app.main:app --host 0.0.0.0 --port 8000
