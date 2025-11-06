from __future__ import annotations
import io, os, time
from pathlib import Path
from typing import Dict, Any, List, Tuple
import requests
import streamlit as st

st.set_page_config(page_title="Invoice Pipeline – Upload & Convert", layout="wide")
TTL_SECONDS = 5 * 60
AUTO_REFRESH_MS = 30_000

SECRETS_DIR  = (Path(__file__).parent / ".streamlit")
SECRETS_FILE = SECRETS_DIR / "secrets.toml"

def _read_toml_text(p: Path) -> Dict[str, Any]:
    try:
        if not p.exists():
            return {}
        try:
            import tomllib
            return tomllib.loads(p.read_text(encoding="utf-8"))
        except Exception:
            import tomli
            return tomli.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _write_backend_url(url: str) -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_FILE.write_text(f'backend_url = "{url.strip()}"\n', encoding="utf-8")

def _resolve_backend_url() -> str:
    env = os.environ.get("BACKEND_URL", "").strip()
    if env:
        return env
    toml = _read_toml_text(SECRETS_FILE)
    if "backend_url" in toml and str(toml["backend_url"]).strip():
        return str(toml["backend_url"]).strip()
    return ""

def _join(base: str, path: str) -> str:
    return base.rstrip("/") + (path if path.startswith("/") else f"/{path}")

def _init_state():
    if "uploads" not in st.session_state:
        st.session_state["uploads"] = {}
    if "last_activity" not in st.session_state:
        st.session_state["last_activity"] = time.time()

def _cleanup_ttl() -> int:
    now = time.time()
    removed = 0
    for name, meta in list(st.session_state["uploads"].items()):
        if now - meta["uploaded_at"] >= TTL_SECONDS:
            st.session_state["uploads"].pop(name, None)
            removed += 1
    return removed

def _fmt_left(ts: float) -> str:
    left = max(0, TTL_SECONDS - int(time.time() - ts))
    m, s = divmod(left, 60)
    return f"{m:02d}:{s:02d}"

def _add_uploads(files: List) -> tuple[list[str], list[str]]:
    added, replaced = [], []
    for f in files or []:
        name = Path(f.name).name.strip()
        data = f.read()
        existed = name in st.session_state["uploads"]
        st.session_state["uploads"][name] = {
            "data": data,
            "size": len(data),
            "uploaded_at": time.time(),
        }
        if existed:
            replaced.append(name)
        else:
            added.append(name)
    st.session_state["last_activity"] = time.time()
    return added, replaced

def _clear_all():
    st.session_state["uploads"].clear()
    st.session_state["last_activity"] = time.time()

st.title("🧾 Invoice Pipeline – Upload & Convert")

autoref = getattr(st, "autorefresh", None) or getattr(st, "st_autorefresh", None)
if autoref:
    autoref(interval=AUTO_REFRESH_MS, key="auto_gc")

with st.expander("🔌 Kết nối Backend", expanded=True):
    backend_url_input = st.text_input(
        "Backend URL",
        value=_resolve_backend_url(),
        placeholder="https://<service>-<hash>-<region>.a.run.app",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Lưu URL"):
            if backend_url_input.strip().startswith("http"):
                _write_backend_url(backend_url_input.strip())
                st.success("Đã lưu URL backend.")
            else:
                st.error("Vui lòng nhập URL hợp lệ.")
    with c2:
        if st.button("🔗 Kiểm tra /health"):
            url = backend_url_input.strip()
            if not url:
                st.error("Chưa có Backend URL.")
            else:
                try:
                    r = requests.get(_join(url, "/health"), timeout=12)
                    st.info(f"Response: {r.status_code} — {r.text[:500]}")
                except Exception as e:
                    st.error(f"Response: None — {e!r}")
    if backend_url_input.strip():
        st.info("Đang dùng: " + backend_url_input.strip())

_init_state()
removed = _cleanup_ttl()
if removed:
    st.info(f"🧹 Đã xoá {removed} file hết hạn (TTL {TTL_SECONDS//60} phút).")

st.subheader("Chọn nhiều XML (d1…d5, …)")
files = st.file_uploader("Drag and drop files here", type=["xml"], accept_multiple_files=True)
if files:
    added, replaced = _add_uploads(files)
    if added:
        st.success("✅ Thêm: " + ", ".join(added))
    if replaced:
        st.warning("♻️ Ghi đè: " + ", ".join(replaced))

if st.session_state["uploads"]:
    import pandas as pd
    df = pd.DataFrame([
        {"Tên file": name,
         "Kích thước (KB)": round(meta["size"]/1024, 1),
         "Còn lại (mm:ss)": _fmt_left(meta["uploaded_at"])}
        for name, meta in st.session_state["uploads"].items()
    ])
    st.caption("Các file đang giữ tạm (tự xoá sau 5 phút không tương tác):")
    st.dataframe(df, use_container_width=True, hide_index=True)
    if st.button("🧽 Xoá tất cả file (ngay)"):
        _clear_all()
        st.success("Đã xoá tất cả file.")
        st.stop()
else:
    st.caption("Chưa có file nào.")
    merge_to_one = st.checkbox("Gộp nhiều file thành 1 Excel", value=True)

if st.button("🚀 Convert"):
    backend = (backend_url_input.strip() or _resolve_backend_url())
    if not backend:
        st.error("Chưa cấu hình Backend URL."); st.stop()
    if not st.session_state["uploads"]:
        st.error("Vui lòng chọn ít nhất 1 tệp XML."); st.stop()

    try:
        form_files = [
            ("files", (name, io.BytesIO(meta["data"]), "application/xml"))
            for name, meta in st.session_state["uploads"].items()
        ]
        data = {"merge_to_one": "true" if merge_to_one else "false"}
        resp = requests.post(_join(backend, "/pipeline/xml-to-xlsx"),
                             files=form_files, data=data, timeout=120)
    except Exception as e:
        st.error(f"Không gọi được backend: {e}"); st.stop()

    if resp.status_code != 200:
        st.error(f"Lỗi từ backend ({resp.status_code}): {resp.text[:500]}"); st.stop()

    ctype = resp.headers.get("Content-Type", "application/octet-stream")
    cd = resp.headers.get("Content-Disposition", "")
    fname = "Data.xlsx"
    if "filename=" in cd:
        fname = cd.split("filename=")[-1].strip("\"'; ")
    st.success("✅ Hoàn tất. Bấm nút để tải xuống.")
    st.download_button("⬇️ Download", data=resp.content, file_name=fname, mime=ctype)
    _clear_all()

st.markdown("""
<div style="text-align:center;color:#6c757d;margin-top:32px;">
  © 2025 Chuong Minh. All rights reserved. ·
  <a href="https://m.me/michng99" target="_blank">Messenger</a>
</div>""", unsafe_allow_html=True)
