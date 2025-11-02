from __future__ import annotations
import json, re
from typing import Any, Dict, List, Tuple
from jsonpath_ng import parse as jp_parse

def jp(expr): return jp_parse(expr)
def jget(doc, expr): return [m.value for m in jp(expr).find(doc)]
def first(vs): return "" if not vs else vs[0]
def fnum(x):
    try: return float(str(x).replace(",","").strip())
    except: return 0.0
def roundn(x, n): return float(f"{x:.{n}f}")

DIGITS_KEYS = re.compile(r"(decimal\s*digits|digits|precision)", re.I)

def find_digits(item, d_money=0, d_vat=0)->Tuple[int,int]:
    money, vat = d_money, d_vat
    tlist = (item or {}).get("TTKhac",{}).get("TTin")
    if isinstance(tlist, list):
        for t in tlist:
            k=str(t.get("TTruong","")); v=str(t.get("DLieu",""))
            if DIGITS_KEYS.search(k):
                nums=re.findall(r"\d+", v)
                if nums:
                    d=int(nums[0]); kl=k.lower()
                    if "vat" in kl: vat=d
                    else: money=d
    return money, vat

def detect_note(inv: Dict[str,Any])->str:
    s=json.dumps(inv, ensure_ascii=False)
    if "Điều chỉnh cho hóa đơn Mẫu số" in s: return "Hoá đơn điều chỉnh"
    if "Thay thế cho hóa đơn Mẫu số" in s: return "Hoá đơn thay thế"
    return "Hoá đơn mới"

def headers(schema): return [c["header"] for c in schema["xlsx"]["columns"]]

def cell(col, inv, item, dm, dv):
    if "constant" in col:
        return float(col["constant"]) if col.get("type")=="float" else col["constant"]
    if col.get("compute")=="VAT":
        th=fnum(first(jget(item,"$.ThTien"))); return roundn(th*0.08, dv)
    if col.get("compute")=="TOTAL":
        upa=0.0
        for t in jget(item, "$.TTKhac.TTin[*]"):
            if isinstance(t, dict) and t.get("TTruong")=="UnitPriceAfterTax":
                upa=fnum(t.get("DLieu")); break
        sl=fnum(first(jget(item,"$.SLuong")))
        if upa==0.0:
            per = (fnum(first(jget(item,"$.ThTien")))/sl) if sl else 0.0
            upa = per*1.08
        return roundn(upa*sl, dm)
    if col.get("compute")=="NOTE":
        return detect_note(inv)

    path=col.get("path")
    if not path: return ""
    ctx = item if (path.startswith("$.") and "$.HDon" not in path) else inv
    val = first(jget(ctx, path))
    return roundn(fnum(val), dm) if col.get("type")=="float" else val

def flatten_invoice(inv: Dict[str,Any], schema: Dict[str,Any])->List[List[Any]]:
    base = schema["xlsx"]["explode"]["base"]
    cols = schema["xlsx"]["columns"]
    dmoney = int(schema["xlsx"].get("defaults",{}).get("decimals_money",0))
    dvat   = int(schema["xlsx"].get("defaults",{}).get("decimals_vat",0))
    items = jget(inv, base)
    rows=[]
    for it in items:
        dm,dv = find_digits(it, dmoney, dvat)
        rows.append([cell(c, inv, it, dm, dv) for c in cols])
    return rows
