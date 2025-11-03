from __future__ import annotations
import io, time, os
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

import requests
import streamlit as st

# ===== Cấu hình phiên =====
TTL_SECONDS = 5 * 60
# FIX: secrets nằm ngay trong thư mục app, KHÔNG phải fe/.streamlit
SECRETS_DIR  = Path(".streamlit")
SECRETS_FILE = SECRETS_DIR / "secrets.toml"

st.set_page_config(page_title="Invoice Pipeline – Upload & Convert", layout="wide")

# ---------- Helpers lưu/đọc BACKEND_URL ----------
def _read_secrets_raw() -> Dict[str, Any]:
    try:
        import tomllib
        if SECRETS_FILE.exists():
            return tomllib.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _write_backend_url(url: str) -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_FILE.write_text(f'backend_url = "{url}"\n', encoding="utf-8")

def get_backend_url() -> str:
    if "backend_url" in st.session_state and st.session_state["backend_url"]:
        return st.session_state["backend_url"]
    raw = _read_secrets_raw()
    if raw.get("backend_url"):
        st.session_state["backend_url"] = raw["backend_url"]
        return raw["backend_url"]
    env = os.getenv("BACKEND_URL", "").strip()
    if env:
        st.session_state["backend_url"] = env
        return env
    return ""

# ---------- State & TTL ----------
def init_state() -> None:
    st.session_state.setdefault("uploads", {})        # name -> {"content": bytes, "ts": float}
    st.session_state.setdefault("last_activity", time.time())
    st.session_state.setdefault("msg", "")
    # FIX: để reset uploader
    st.session_state.setdefault("uploader_key", 0)

def touch() -> None:
    st.session_state["last_activity"] = time.time()

def clear_session(reason: str = "") -> None:
    st.session_state["uploads"] = {}
    st.session_state["msg"] = reason
    st.session_state["uploader_key"] += 1           # reset uploader
    st.rerun()

def cleanup_ttl() -> None:
    now = time.time()
    # hết tương tác 5 phút => reset
    if now - st.session_state.get("last_activity", now) > TTL_SECONDS:
        clear_session("Phiên đã hết hạn 5 phút không tương tác. Đã làm mới.")
    # xóa từng file quá TTL
    for name in list(st.session_state["uploads"].keys()):
        if now - st.session_state["uploads"][name]["ts"] > TTL_SECONDS:
            del st.session_state["uploads"][name]

# ---------- Backend calls ----------
def check_health(base_url: str) -> Tuple[Optional[int], str]:
    if not base_url:
        return None, "Chưa có BACKEND_URL"
    try:
        r = requests.get(base_url.rstrip("/") + "/health", timeout=10)
        return r.status_code, r.text
    except Exception as e:
        return None, f"Không gọi được: {e}"

def post_convert(base_url: str, merge_to_one: bool) -> requests.Response:
    files: List[Tuple[str, Tuple[str, io.BytesIO, str]]] = []
    for name, meta in st.session_state["uploads"].items():
        files.append(("xml_files", (name, io.BytesIO(meta["content"]), "application/xml")))
    return requests.post(
        base_url.rstrip("/") + "/pipeline/xml-to-xlsx",
        files=files,
        data={"merge_to_one": str(merge_to_one).lower()},
        timeout=120,
    )

# ===== App =====
init_state()
cleanup_ttl()
st.info("Trang tự làm mới khi có tương tác. Không thao tác 5 phút sẽ auto reset & xóa file tạm.", icon="⏱️")

with st.expander("🧰 Kết nối Backend", expanded=True):
    url_input = st.text_input(
        "Backend URL",
        value=get_backend_url(),
        help="Ví dụ: https://invoice-pipeline-xxxx.asia-southeast1.run.app",
        placeholder="https://<service>-<hash>-<region>.a.run.app",
    )
    c1, c2, c3, c4 = st.columns([1,1,3,3])
    with c1:
        if st.button("💾 Lưu URL", use_container_width=True):
            if not url_input.strip():
                st.warning("Vui lòng nhập URL backend.", icon="⚠️")
            else:
                _write_backend_url(url_input.strip())
                st.session_state["backend_url"] = url_input.strip()
                touch()
                st.success("Đã lưu URL backend. Không cần tải lại trang.", icon="✅")
    with c2:
        if st.button("🩺 Kiểm tra /health", use_container_width=True):
            touch()
            sc, txt = check_health(get_backend_url())
            if sc == 200:
                st.success(f"200 OK — {txt}", icon="✅")
            else:
                st.error(f"{sc} — {txt}", icon="❌")
    with c3:
        cur = get_backend_url()
        if cur:
            st.markdown(f"**Đang dùng:** {cur}")
    with c4:
        st.caption("Nếu giao diện chưa phản ánh URL mới, bấm lại “Kiểm tra /health” hoặc refresh.")

if st.session_state.get("msg"):
    st.info(st.session_state["msg"], icon="ℹ️")
    st.session_state["msg"] = ""

st.markdown("### Chọn nhiều XML (d1…d5, …)")
uploaded = st.file_uploader(
    "Drag & drop hoặc Browse XML",
    type=["xml"], accept_multiple_files=True, label_visibility="collapsed",
    key=f"uploader_{st.session_state['uploader_key']}"   # FIX: reset uploader
)

# Nhận file, chống trùng tên
if uploaded:
    skipped, added = [], []
    for f in uploaded:
        name = (f.name or "").strip()
        if not name:
            continue
        if name in st.session_state["uploads"]:
            skipped.append(name)
            continue
        st.session_state["uploads"][name] = {"content": f.getvalue(), "ts": time.time()}
        added.append(name)
    touch()
    if added:
        st.success("Đã nhận: " + ", ".join(added), icon="✅")
    if skipped:
        st.warning("Đã tồn tại: " + ", ".join(skipped) + ". Bỏ qua.", icon="⚠️")

# Bảng file đang giữ tạm + TTL còn lại
if st.session_state["uploads"]:
    import pandas as pd, time as _t
    now = _t.time()
    rows = []
    for i, (name, meta) in enumerate(st.session_state["uploads"].items(), start=1):
        ttl_left = max(0, int(TTL_SECONDS - (now - meta["ts"])))
        rows.append({"#": i, "Tên file": name, "Còn lại (giây)": ttl_left})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
else:
    st.caption("Chưa có file nào trong phiên.")

# Xóa ngay
cL, _ = st.columns([1,4])
with cL:
    if st.button("🧹 Xoá tất cả file (ngay)", type="secondary"):
        st.session_state["uploads"] = {}
        st.session_state["uploader_key"] += 1          # FIX: reset uploader
        touch()
        st.success("Đã xoá tất cả file trong phiên.", icon="✅")
        st.rerun()                                     # FIX: refresh ngay

merge_to_one = st.checkbox("Gộp nhiều file thành 1 Excel", value=True)

# Convert
if st.button("🚀 Convert", type="primary"):
    touch()
    base_url = get_backend_url()
    if not base_url:
        st.error("Chưa cấu hình Backend URL.", icon="❌")
    elif not st.session_state["uploads"]:
        st.warning("Vui lòng chọn ít nhất 1 tệp XML.", icon="⚠️")
    else:
        try:
            resp = post_convert(base_url, merge_to_one)
            if resp.status_code == 200:
                cdisp = resp.headers.get("Content-Disposition", "")
                ctype = resp.headers.get("Content-Type", "")
                fname = "Data.xlsx" if "spreadsheetml.sheet" in ctype else "excels.zip"
                if "filename=" in cdisp:
                    fname = cdisp.split("filename=",1)[1].strip().strip("\"' ")
                st.success("Hoàn tất. Bấm nút để tải xuống.", icon="✅")
                st.download_button("⬇️ Download", data=resp.content, file_name=fname, mime=ctype or "application/octet-stream")
            else:
                st.error(f"Lỗi từ backend ({resp.status_code}): {resp.text}", icon="❌")
        except Exception as e:
            st.error(f"Không gọi được backend: {e}", icon="❌")

st.caption("Tip: URL backend được lưu ở `.streamlit/secrets.toml`. Có thể set nhanh bằng biến môi trường `BACKEND_URL`.")
