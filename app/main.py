from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import pandas as pd, xmltodict, io

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True, "version": "v2.3-keep-all-tchat"}

def _as_list(x):
    if x is None: return []
    return x if isinstance(x, list) else [x]

def rows_from_xml(xml_bytes: bytes):
    d = xmltodict.parse(xml_bytes)
    hdon = d.get("HDon", {})
    ttchung = hdon.get("DLHDon", {}).get("TTChung", {}) or {}
    nd   = hdon.get("DLHDon", {}).get("NDHDon", {}) or {}
    dshh = nd.get("DSHHDVu", {}) or {}
    items = _as_list(dshh.get("HHDVu"))

    # tiền tệ & tỷ giá ở TTChung
    dvtt  = (ttchung.get("DVTTe") or "").strip()
    tg    = (ttchung.get("TGia") or "1").strip()

    rows = []
    for it in items:
        tchat = (it.get("TChat") or "").strip()
        row = {
            "Mẫu số":       ttchung.get("KHMSHDon") or "",
            "Kí hiệu hóa đơn": ttchung.get("KHHDon") or "",
            "Số hóa đơn":   ttchung.get("SHDon") or "",
            "Ngày hóa đơn": ttchung.get("NLap") or "",
            "MST người bán": (nd.get("NBan", {}) or {}).get("MST") or "",
            "Tên người bán": (nd.get("NBan", {}) or {}).get("Ten") or "",
            "Địa chỉ người bán": (nd.get("NBan", {}) or {}).get("DChi") or "",
            "Mã hàng":      (it.get("MHHDVu") or "").strip(),
            "Tên hàng":     (it.get("THHDVu") or "").strip(),
            "Đơn vị tính":  (it.get("DVTinh") or "").strip(),
            "Số lượng":     float((it.get("SLuong") or 0) or 0),
            "Đơn giá":      float((it.get("DGia") or 0) or 0),
            "Tiền hàng":    float((it.get("ThTien") or 0) or 0),
            "Thuế suất":    (it.get("TSuat") or "").replace("%","").strip().replace(",","."),
            "Tiền thuế":    float(((it.get("TTKhac") or {}).get("TTin", [{}]) if False else 0) or 0),  # sẽ tính lại bên dưới
            "Cộng tiền":    0,  # sẽ tính lại bên dưới
            "Ghi chú":      "Hóa đơn mới",
            "Đơn vị tiền":  dvtt,
            "Tỷ giá":       float(tg) if tg else 1.0,
            "Cờ (Tchat)":   tchat
        }
        # Thuế suất dạng '8' hoặc '8%'
        try:
            vat_rate = float(row["Thuế suất"]) / (100.0 if float(row["Thuế suất"]) > 1 else 1)
        except:
            vat_rate = 0.0
        # nếu thiếu tiền thuế -> tự tính
        row["Tiền thuế"] = round(row["Tiền hàng"] * vat_rate, 0)
        row["Cộng tiền"] = round(row["Tiền hàng"] + row["Tiền thuế"], 0)

        rows.append(row)
    return rows

@app.post("/pipeline/xml-to-xlsx")
async def xml_to_xlsx(xml_files: list[UploadFile] = File(...)):
    all_rows = []
    for f in xml_files:
        xml_bytes = await f.read()
        all_rows.extend(rows_from_xml(xml_bytes))

    if not all_rows:
        return JSONResponse({"ok": True, "rows": 0})

    df = pd.DataFrame(all_rows)

    # sắp xếp: giữ nguyên thứ tự xuất hiện (STT), nhưng ở đây không có, nên để nguyên
    # format xuất
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as w:
        df.to_excel(w, sheet_name="Mẫu số", index=False)
    out.seek(0)
    return {"ok": True, "rows": len(df)}
