import io
from typing import List
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
import pandas as pd
import xmltodict

VERSION = "v2.1-currency-rate"

app = FastAPI()

def _fnum(x, default=0.0):
    try:
        return float(str(x).replace(",", ""))
    except:
        return default

def _ttin(ttkhac, key):
    if not ttkhac:
        return ""
    items = ttkhac.get("TTin", [])
    if isinstance(items, dict):
        items = [items]
    for it in items:
        if it.get("TTruong") == key:
            return it.get("DLieu", "")
    return ""

def _note(raw: str):
    if "Điều chỉnh cho hóa đơn" in raw or "Điều chỉnh cho hoá đơn" in raw:
        return "Hoá đơn điều chỉnh"
    if "Thay thế cho hóa đơn" in raw or "Thay thế cho hoá đơn" in raw:
        return "Hoá đơn thay thế"
    return "Hoá đơn mới"

HEADERS = [
    "Mẫu số","KH hóa đơn","Số hóa đơn","Ngày hóa đơn",
    "MST người bán","Tên người bán","ĐC người bán",
    "Mã hàng","Tên hàng",
    "Đơn vị tính","Số lượng","Đơn giá","Tiền hàng",
    "Thuế suất","Tiền thuế","Cộng tiền",
    "Ghi chú","Đơn vị tiền","Tỷ giá"
]

def flatten(doc: dict):
    hdon = doc.get("HDon", {})
    dlh  = hdon.get("DLHDon", {})
    ttch = dlh.get("TTChung", {})
    nd   = dlh.get("NDHDon", {})
    ds   = nd.get("DSHHDVu", {}).get("HHDVu", [])
    if isinstance(ds, dict):
        ds = [ds]

    # cấu hình làm tròn
    ttk_root = dlh.get("TTKhac", {})
    dec_money = int(_fnum(_ttin(ttk_root, "AmountDecimalDigits") or 0, 0))
    dec_rate  = int(_fnum(_ttin(ttk_root, "ExchangRateDecimalDigits") or 2, 2))

    # Thuế suất chuẩn hoá
    rate_tax = 0.08

    # Đơn vị tiền & Tỷ giá từ TTChung
    dvtt = ttch.get("DVTTe", "")
    tgia = _fnum(ttch.get("TGia", 1.0), 1.0)

    rows = []
    note = _note(str(doc))

    for it in ds:
        # chỉ lấy dòng hàng hoá
        if str(it.get("TChat", "")).strip() != "1":
            continue

        ms   = ttch.get("KHMSHDon", "")
        kh   = ttch.get("KHHDon", "")
        sohd = ttch.get("SHDon", "")
        ngay = ttch.get("NLap", "")

        nban = nd.get("NBan", {})
        mst_ban = nban.get("MST","")
        ten_ban = nban.get("Ten","")
        dc_ban  = nban.get("DChi","")

        mahang  = it.get("MHHDVu","")
        tenhang = it.get("THHDVu","")
        dvt = it.get("DVTinh","")
        sl  = _fnum(it.get("SLuong",0))
        dongia = _fnum(it.get("DGia",0))
        thtien = _fnum(it.get("ThTien",0))

        # VAT & Cộng tiền
        vat_amount = round(thtien * rate_tax, dec_money)
        up_after_tax = _fnum(_ttin(it.get("TTKhac", {}),"UnitPriceAfterTax") or 0)
        if up_after_tax>0 and sl>0:
            total = round(up_after_tax*sl, dec_money)
        else:
            total = round(thtien + vat_amount, dec_money)

        row = [
            ms, kh, sohd, ngay,
            mst_ban, ten_ban, dc_ban,
            mahang, tenhang,
            dvt, sl, round(dongia, dec_money), round(thtien, dec_money),
            rate_tax, vat_amount, total,
            note, dvtt, round(tgia, dec_rate)
        ]
        rows.append(row)
    return rows

def to_df(all_rows: list) -> pd.DataFrame:
    df = pd.DataFrame(all_rows, columns=HEADERS)
    return df

@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}

@app.get("/debug/columns")
def debug_columns():
    return {"version": VERSION, "columns": HEADERS}

@app.post("/pipeline/xml-to-xlsx")
async def xml_to_xlsx(xml_files: List[UploadFile] = File(...)):
    all_rows = []
    for f in xml_files:
        content = await f.read()
        doc = xmltodict.parse(content)
        all_rows += flatten(doc)

    df = to_df(all_rows)
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Data")
    bio.seek(0)
    return StreamingResponse(
        bio,
        headers={
            "Content-Disposition": 'attachment; filename="Data.xlsx"',
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
    )
