# main.py
import logging
import json
import requests
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, Response
import os

# ---------------- 可自訂的查詢預設值 ----------------
# 以下為 /devices API 的預設查詢條件，
# 若前端（或瀏覽器 URL）未帶入相對應參數時，將採用這些值。
#
# 🧭 /devices 基本呼叫格式：
#   http://<HOST>:<PORT>/devices?prefix=<開頭>&suffix=<結尾1>,<結尾2>&query=<關鍵字>&limit=<筆數>
#
# 🔍 範例：
#   http://localhost:8099/devices?prefix=sensor.zp2_&suffix=_p25,_co2
#   → 取出所有 entity_id 以 sensor.zp2_ 開頭，且結尾為 _p25 或 _co2 的實體
#
#   若網址沒帶 prefix/suffix/query/limit，則使用以下預設值。

DEFAULT_QUERY  = ""                   # 關鍵字（比對 entity_id 或 friendly_name）
DEFAULT_PREFIX = "sensor.testprint_"  # entity_id 開頭條件，例：sensor.zp2_*
DEFAULT_SUFFIX = "_action"            # entity_id 結尾條件，可多個（逗號分隔）
DEFAULT_LIMIT  = 100                  # 最多回傳幾筆裝置資料（防止過量）

# ---------------- Log參數設定 ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logging.getLogger().setLevel(logging.INFO)

# ---------------- HA API 設定 ----------------
# 使用 Supervisor 內建 API token 進行授權。
# 需在 add-on 的 config.yaml 中啟用：
#   homeassistant_api: true
# BASE_URL 指向 Home Assistant Core API 的內部位址（容器內固定）。
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
BASE_URL = "http://supervisor/core/api"
HEADERS = {
    "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
    "Content-Type": "application/json",
}
if not SUPERVISOR_TOKEN:
    logging.warning("⚠️ SUPERVISOR_TOKEN 未提供，請確認 add-on 啟用了 homeassistant_api: true")

# ---------------- Flask HTTP 設定 ----------------
# Flask 在容器內監聽的 IP 與 Port。
# HTTP_HOST = "0.0.0.0" → 允許所有網路介面連線（外部可訪問）
# HTTP_PORT = 8099 → 容器內部埠號；會在 add-on config.yaml 透過 ports 映射到外部（例如 8088:8099）
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 8099

# ---------------- 核心：查清單 / 讀欄位 ----------------
def _get_all_states():
    """GET /api/states 取回全部實體狀態。"""
    if not HEADERS.get("Authorization"):
        raise RuntimeError("HA Token 未設定（HEADERS 無 Authorization）")
    url = f"{BASE_URL}/states"
    resp = requests.get(url, headers=HEADERS, timeout=5)
    resp.raise_for_status()
    return resp.json()

def _parse_suffixes_from_request():
    """支援 ?suffix=a&suffix=b 與 ?suffix=a,b 兩種寫法；沒帶就用 DEFAULT_SUFFIX（亦可逗號）"""
    suffix_params = request.args.getlist("suffix")
    suffixes = []
    if suffix_params:
        for s in suffix_params:
            suffixes.extend([x.strip() for x in s.split(",") if x.strip()])
    else:
        suffixes = [x.strip() for x in (DEFAULT_SUFFIX or "").split(",") if x.strip()]
    return suffixes

def _match_suffix(entity_id: str, suffixes: list[str]):
    """
    從 entity_id 尾端判斷命中的 suffix。
    回傳 (matched_suffix, trailing)：
      matched_suffix = 例如 'cttm_usedwatercontrol'
      trailing       = 真正要從尾端裁掉的字串（可能是 '_'+suffix 或 suffix）
    無命中回 (None, None)
    """
    if not suffixes:
        return None, None
    for s in suffixes:
        if not s:
            continue
        if entity_id.endswith("_" + s):
            return s, "_" + s
        if entity_id.endswith(s):
            return s, s
    return None, None

# ---------------- Flask API ----------------
app = Flask(__name__, template_folder="templates")

@app.get("/status")
def status_page():
    """顯示列印狀態面板"""
    return render_template("status.html")

@app.get("/health")
def health():
    return jsonify({"ok": True, "ha_base": BASE_URL})

@app.get("/devices")
def devices_view():
    query   = request.args.get("query", DEFAULT_QUERY).strip()
    prefix  = request.args.get("prefix", DEFAULT_PREFIX).strip()
    limit   = int(request.args.get("limit", DEFAULT_LIMIT))
    suffixes = _parse_suffixes_from_request()

    try:
        states = _get_all_states()
        devices_map = {}  # device_id -> {"device_id":..., "metrics": {...}}

        for s in states:
            eid = s.get("entity_id") or ""
            if prefix and not eid.startswith(prefix):
                continue

            # 關鍵字（entity_id 或 friendly_name）
            if query:
                name = (s.get("attributes", {}).get("friendly_name") or "")
                q = query.lower()
                if q not in eid.lower() and q not in name.lower():
                    continue

            # 後綴比對（拿到命中的 suffix 與實際要裁掉的 trailing）
            matched_suffix, trailing = _match_suffix(eid, suffixes)
            if not matched_suffix:
                continue

            # 去掉 domain 取得 object_id（sensor.3drp_211242142_state -> 3drp_211242142_state）
            base = eid.split(".", 1)[1] if "." in eid else eid

            # 精準裁掉尾巴（依 trailing 長度），再把可能殘留的底線收乾淨
            base_wo_suffix = base[: -len(trailing)] if trailing else base
            base_wo_suffix = base_wo_suffix.rstrip("_")

            # 正常化裝置標籤
            device_label = base_wo_suffix

            # 收集 metrics（key 就是完整 suffix：matched_suffix）
            row = devices_map.setdefault(device_label, {"device_id": device_label, "metrics": {}})
            row["metrics"][matched_suffix] = {
                "value": s.get("state"),
                "last_updated": s.get("last_updated"),
            }

        # 輸出整理
        devices_list = list(devices_map.values())
        devices_list.sort(key=lambda d: d["device_id"])
        if limit and len(devices_list) > limit:
            devices_list = devices_list[:limit]

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "requested": {
                "prefix": prefix,
                "suffixes": suffixes
            },
            "devices": devices_list
        }
        return jsonify(payload)

    except requests.HTTPError as e:
        return jsonify({"error": f"HTTP {e.response.status_code}", "detail": e.response.text[:300]}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
if __name__ == "__main__":
    logging.info(f"HA base: {BASE_URL}")
    logging.info(f"HTTP listening on {HTTP_HOST}:{HTTP_PORT}")
    logging.info(f"Default filters → query='{DEFAULT_QUERY}', prefix='{DEFAULT_PREFIX}', suffix='{DEFAULT_SUFFIX}'")
    app.run(host=HTTP_HOST, port=HTTP_PORT, debug=False, threaded=True)
