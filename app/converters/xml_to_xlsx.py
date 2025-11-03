from __future__ import annotations
import io, zipfile
from decimal import Decimal
from typing import List, Tuple
from xml.etree import ElementTree as ET

import pandas as pd
from fastapi.responses import StreamingResponse

# Cấu trúc cột CHUẨN (giống Data-Master ban đầu của em)
COLUMN_ORDER = [
    "Mẫu số",
    "KH hóa đơn",
    "Số hóa đơn",
    "Ngày hóa đơn",
    "ST người bán",
    "Tên người bán",
    "ĐC người bán",
    "C người bán",
    "Mã hàng",
    "Tên hàng",
    "Đơn vị tính",
    "Số lượng",
    "Đơn giá",
    "Tiền hàng",
    "Thuế suất",
    "Tiền thuế",
    "Cộng tiền",
    "Ghi chú",
    "Đơn vị tiền",
    "Tỷ giá",
    "Cờ (Tchat)",
]

def _num(v):
    try:
        return float(Decimal(str(v)))
    except Exception:
        return None

def _txt(x):
    return (x or "").strip()

def _find_text(node: ET.Element, path: str):
    n = node.find(path)
    return _txt(n.text) if n is not None and n.text is not None else ""

def _parse_invoice(xml_bytes: bytes) -> dict:
    """
    Parse XML hoá đơn (định dạng như em gửi) -> dict nhẹ cho converter.
    Không phụ thuộc xmltodict, dùng ElementTree cho chắc.
    """
    root = ET.fromstring(xml_bytes)

    def f(p):  # find text helper
        n = root.find(p)
        return _txt(n.text) if n is not None and n.text is not None else ""

    # Thông tin chung
    invoice = {
        "KHMSHDon": f("./DLHDon/TTChung/KHMSHDon"),
        "KHHDon":   f("./DLHDon/TTChung/KHHDon"),
        "SHDon":    f("./DLHDon/TTChung/SHDon"),
        "NLap":     f("./DLHDon/TTChung/NLap"),
        "DVTTe":    f("./DLHDon/TTChung/DVTTe") or "VND",
        "TGia":     f("./DLHDon/TTChung/TGia") or "1",
    }

    # Người bán
    nban = root.find("./DLHDon/NDHDon/NBan")
    invoice["NBan"] = {
        "Ten":  _find_text(nban, "Ten") if nban is not None else "",
        "MST":  _find_text(nban, "MST") if nban is not None else "",
        "DChi": _find_text(nban, "DChi") if nban is not None else "",
    }

    # Hàng hoá
    items_parent = root.find("./DLHDon/NDHDon/DSHHDVu")
    items = []
    if items_parent is not None:
        for it in items_parent.findall("./HHDVu"):
            items.append({
                "TChat":   _find_text(it, "TChat"),
                "MHHDVu":  _find_text(it, "MHHDVu"),
                "THHDVu":  _find_text(it, "THHDVu"),
                "DVTinh":  _find_text(it, "DVTinh"),
                "SLuong":  _find_text(it, "SLuong") or "0",
                "DGia":    _find_text(it, "DGia") or "0",
                "ThTien":  _find_text(it, "ThTien") or "0",
                "TSuat":   _find_text(it, "TSuat"),
                "VATAmount": _find_text(it, "./TTKhac/VATAmount") or "0",
                "Amount":    _find_text(it, "./TTKhac/Amount") or "0",
            })
    invoice["Items"] = items
    return invoice

def _rows_from_invoice(inv: dict) -> list[dict]:
    ms  = inv.get("KHMSHDon") or ""
    kh  = inv.get("KHHDon") or ""
    so  = inv.get("SHDon") or ""
    ngay = inv.get("NLap") or ""
    cur = inv.get("DVTTe") or "VND"
    rate = inv.get("TGia") or 1
    seller = inv.get("NBan") or {}
    s_mst  = seller.get("MST") or ""
    s_name = seller.get("Ten") or ""
    s_addr = seller.get("DChi") or ""
    ghichu = "Hoá đơn mới"

    items = inv.get("Items") or []
    rows = []

    # a) Các dòng mô tả TChat=4 (nếu có) -> xuất trước để giữ bố cục mong muốn
    for it in items:
        if (it.get("TChat") or "").strip() == "4":
            row = {k: "" for k in COLUMN_ORDER}
            row.update({
                "Mẫu số": ms, "KH hóa đơn": kh, "Số hóa đơn": so, "Ngày hóa đơn": ngay,
                "ST người bán": s_mst, "Tên người bán": s_name, "ĐC người bán": s_addr,
                "C người bán": "",
                "Mã hàng": "", "Tên hàng": it.get("THHDVu") or "", "Đơn vị tính": "",
                "Số lượng": _num(it.get("SLuong") or 0) or 0,
                "Đơn giá":  _num(it.get("DGia") or 0) or 0,
                "Tiền hàng": _num(it.get("ThTien") or 0) or 0,
                "Thuế suất": (it.get("TSuat") or "").replace("%","").replace(",",".") if it.get("TSuat") else "",
                "Tiền thuế": _num(it.get("VATAmount") or 0) or 0,
                "Cộng tiền": _num(it.get("Amount") or 0) or 0,
                "Ghi chú": ghichu, "Đơn vị tiền": cur, "Tỷ giá": _num(rate) or 1,
                "Cờ (Tchat)": 4,
            })
            rows.append(row)

    # b) Hàng hóa còn lại
    for it in items:
        if (it.get("TChat") or "").strip() == "4":
            continue
        row = {k: "" for k in COLUMN_ORDER}
        row.update({
            "Mẫu số": ms, "KH hóa đơn": kh, "Số hóa đơn": so, "Ngày hóa đơn": ngay,
            "ST người bán": s_mst, "Tên người bán": s_name, "ĐC người bán": s_addr,
            "C người bán": "",
            "Mã hàng": it.get("MHHDVu") or "",
            "Tên hàng": it.get("THHDVu") or "",
            "Đơn vị tính": it.get("DVTinh") or "",
            "Số lượng": _num(it.get("SLuong") or 0) or 0,
            "Đơn giá":  _num(it.get("DGia") or 0) or 0,
            "Tiền hàng": _num(it.get("ThTien") or 0) or 0,
            "Thuế suất": (it.get("TSuat") or "").replace("%","").replace(",",".") if it.get("TSuat") else "",
            "Tiền thuế": _num(it.get("VATAmount") or 0) or 0,
            "Cộng tiền": _num(it.get("Amount") or 0) or 0,
            "Ghi chú": ghichu, "Đơn vị tiền": cur, "Tỷ giá": _num(rate) or 1,
            "Cờ (Tchat)": _num(it.get("TChat")) if (it.get("TChat") or "").isdigit() else "",
        })
        rows.append(row)

    return rows

def _df_to_xlsx_stream(rows: list[dict], sheet_name="Data") -> io.BytesIO:
    df = pd.DataFrame(rows)
    # Khóa thứ tự cột, thêm cột thiếu
    df = df.reindex(columns=COLUMN_ORDER)
    # Chuẩn hóa numeric
    for c in ["Số lượng","Đơn giá","Tiền hàng","Thuế suất","Tiền thuế","Cộng tiền","Tỷ giá","Cờ (Tchat)"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
        df.to_excel(wr, index=False, sheet_name=sheet_name)
    buf.seek(0)
    return buf

def _merge_many_to_one(list_rows: List[List[dict]]) -> io.BytesIO:
    """Gộp nhiều hóa đơn -> 1 DataFrame theo COLUMN_ORDER rồi xuất 1 Excel."""
    all_rows = []
    for rows in list_rows:
        all_rows.extend(rows)
    return _df_to_xlsx_stream(all_rows, sheet_name="Data")

def _read_upload_file(f) -> Tuple[str, bytes]:
    """
    Trả về (name, bytes) cho cả Starlette UploadFile, tuple(name, bytes) hoặc bytes.
    """
    if hasattr(f, "read"):  # UploadFile
        b = f.read()
        try:
            f.seek(0)
        except Exception:
            pass
        name = getattr(f, "filename", "input.xml") or "input.xml"
        return name, b
    if isinstance(f, (tuple, list)) and len(f) == 2:
        return str(f[0]), bytes(f[1])
    if isinstance(f, (bytes, bytearray)):
        return "input.xml", bytes(f)
    raise ValueError("Không nhận dạng được kiểu tệp input")

def xml_to_xlsx(files, merge_to_one: bool):
    """
    Hàm chính được app.main gọi.
    - files: list các UploadFile/tuple/bytes
    - merge_to_one: True -> xuất 1 Excel; False -> 1 file => Excel, nhiều file => ZIP
    Trả về StreamingResponse (giữ nguyên kiểu hàm cũ).
    """
    # Build rows per file
    per_file_rows = []
    named_streams = []  # (name.xlsx, bytes)

    for f in files:
        fname, data = _read_upload_file(f)
        inv  = _parse_invoice(data)
        rows = _rows_from_invoice(inv)
        per_file_rows.append(rows)
        xlsx = _df_to_xlsx_stream(rows)
        named_streams.append((f"{fname.rsplit('.',1)[0]}.xlsx", xlsx.getvalue()))

    # Quy tắc trả về
    if merge_to_one or len(named_streams) == 1:
        # 1 file hoặc có chọn gộp -> 1 Excel
        if len(named_streams) == 1 and not merge_to_one:
            name, payload = named_streams[0]
        else:
            name, payload = ("Data-merged.xlsx", _merge_many_to_one(per_file_rows).getvalue())
        stream = io.BytesIO(payload); stream.seek(0)
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}"'}
        )

    # Nhiều file + không gộp -> ZIP
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, payload in named_streams:
            z.writestr(name, payload)
    zbuf.seek(0)
    return StreamingResponse(
        zbuf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="excels.zip"'}
    )
