# main.py
import logging
import json
import requests
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask import Response  # 放在檔案開頭的 import 區域（已有就略過）

# ---------------- 可自訂的查詢預設值 ----------------
DEFAULT_QUERY  = ""             # 關鍵字
DEFAULT_PREFIX = "sensor.zp2_"  # entity_id 開頭條件
DEFAULT_SUFFIX = "_p25"         # entity_id 結尾條件
DEFAULT_LIMIT  = 500            # 最多回傳幾筆

# ---------------- 你的原始參數（沿用） ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

with open("/data/options.json", "r", encoding="utf-8") as f:
    options = json.load(f)

TOPICS = options.get("mqtt_topics", "+/+/data,+/+/control").split(",")
MQTT_BROKER = options.get("mqtt_broker", "core-mosquitto")
MQTT_PORT = int(options.get("mqtt_port", 1883))
MQTT_USERNAME = options.get("mqtt_username", "")
MQTT_PASSWORD = options.get("mqtt_password", "")
LONG_TOKEN = options.get("HA_LONG_LIVED_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {LONG_TOKEN}",
    "Content-Type": "application/json"
}

BASE_URL = options.get("ha_base_url", "http://homeassistant:8123/api").rstrip("/")

# HTTP 伺服器設定
HTTP_HOST = options.get("http_host", "0.0.0.0")
HTTP_PORT = int(options.get("http_port", 8099))
LOG_LEVEL  = options.get("log_level", "INFO").upper()
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

if not LONG_TOKEN:
    logging.warning("⚠️ HA Long-Lived Token 未設定（/data/options.json 的 HA_LONG_LIVED_TOKEN）。")

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

def _device_label_from_base(base: str) -> str:
    """
    base: '3drp_211242142' -> '3DRP_211242142'
    其它前綴不處理大小寫。
    """
    if base.startswith("3drp"):
        return "3DRP" + base[len("3drp"):]
    return base

# ---------------- Flask API ----------------
app = Flask(__name__)

from flask import Response  # 檔頭區有就略過

@app.get("/status")
def status_page():
    html = r"""
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>列印耗材狀態面板</title>
  <style>
    :root{
      --bg:#0b0f14;--panel:#10161d;--panel2:#151c24;--text:#e6eef8;--muted:#9fb3c8;
      --accent:#3ea6ff;--ok:#4ade80;--danger:#ef4444;--border:#223246;
      --shadow:0 10px 24px rgba(0,0,0,.35);
    }
    *{box-sizing:border-box}
    html,body{height:100%}
    body{
      margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Noto Sans,"Helvetica Neue",Arial;
      background:
        radial-gradient(1200px 600px at 100% -20%, #12202d, transparent),
        radial-gradient(800px 500px at -20% 120%, #1a2a38, transparent),
        var(--bg);
      color:var(--text);
    }
    .container{max-width:1200px;margin:28px auto;padding:0 16px}
    .card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow)}
    .header{padding:18px 18px 0}
    h1{margin:0;font-size:22px}
    .sub{color:var(--muted);font-size:13px;margin-top:6px;word-break:break-all}
    .controls{display:flex;gap:10px;align-items:center;padding:14px 18px 18px;flex-wrap:wrap}
    .pill{border:1px solid var(--border);border-radius:999px;padding:6px 10px;font-size:12px;color:var(--muted)}
    .btn{border:1px solid #2b4256;background:linear-gradient(180deg,#15324a,#10273a);color:#d9f1ff;border-radius:10px;padding:8px 12px;cursor:pointer}
    .btn:active{transform:translateY(1px)}
    .table-wrap{border-top:1px solid var(--border)}
    .scroller{max-height:68vh;overflow:auto}
    table{width:100%;border-collapse:separate;border-spacing:0}
    thead th{
      position:sticky;top:0;background:#0f151c;z-index:1;text-align:left;
      font-size:13px;color:#c7d7ea;padding:10px 12px;border-bottom:1px solid var(--border);border-right:1px solid var(--border);white-space:nowrap
    }
    thead th:last-child{border-right:0}
    tbody td{padding:10px 12px;font-size:13px;color:#e6eef8;border-bottom:1px solid #17212c;border-right:1px solid #17212c;white-space:nowrap}
    tbody td:last-child{border-right:0}
    tbody tr:hover td{background:#0f1922}
    .statusbar{display:flex;justify-content:space-between;gap:12px;padding:12px 16px;color:var(--muted);border-top:1px solid var(--border);background:#0c1218;font-size:12px;border-radius:0 0 16px 16px}
    .mono{font-family:ui-monospace,Menlo,Consolas,monospace}
    .err{color:#ffd1d1}
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="header">
        <h1>列印耗材狀態</h1>
        <div class="sub">
          資料來源：
          /devices?prefix=sensor.print_&suffix=_action,_fwversion,_c,_m,_y,_k,_p,_w,_a,_yk,_cm,_z1,_z2
          （每 60 秒自動刷新）
        </div>
      </div>
      <div class="controls">
        <span class="pill">欄位順序：_action → _fwversion → _c → _m → _y → _k → _p → _w → _a → _yk → _cm → _z1 → _z2</span>
        <button id="btnRefresh" class="btn">立即刷新</button>
      </div>
      <div class="table-wrap">
        <div class="scroller">
          <table id="t">
            <thead><tr id="thead"></tr></thead>
            <tbody id="tbody"></tbody>
          </table>
        </div>
      </div>
      <div class="statusbar">
        <div>
          <span>筆數：<span id="count">0</span></span>
          <span style="margin-left:12px">最後更新：<span id="updated">—</span></span>
        </div>
        <div class="mono err" id="msg"></div>
      </div>
    </div>
  </div>

  <script>
    // 1) 依你指定的順序固定欄位
    const SUFFIX_ORDER = ["_action","_fwversion","_c","_m","_y","_k","_p","_w","_a","_yk","_cm","_z1","_z2"];

    // 2) 呼叫 /devices 加上新的 suffix 查詢參數
    const DEVICES_URL = "/devices?prefix=sensor.print_&suffix=_action,_fwversion,_c,_m,_y,_k,_p,_w,_a,_yk,_cm,_z1,_z2";

    const REFRESH_MS = 60000; // 每分鐘刷新

    const elHead = document.getElementById('thead');
    const elBody = document.getElementById('tbody');
    const elCount = document.getElementById('count');
    const elUpdated = document.getElementById('updated');
    const elMsg = document.getElementById('msg');
    const elBtn = document.getElementById('btnRefresh');

    function renderHead() {
      const cols = ["裝置", ...SUFFIX_ORDER];
      elHead.innerHTML = cols.map(c => `<th>${c}</th>`).join("");
    }

    function fmt(v) {
      if (v === null || v === undefined) return "";
      return String(v);
    }

    function toRows(payload) {
      const rows = [];
      const devices = Array.isArray(payload?.devices) ? payload.devices : [];
      for (const d of devices) {
        const id = d?.device_id ?? "";
        const m = d?.metrics ?? {};
        const row = { device: id };
        for (const sfx of SUFFIX_ORDER) {
          row[sfx] = m[sfx]?.value ?? ""; // 只取 value
        }
        rows.push(row);
      }
      return rows;
    }

    function renderBody(rows) {
      if (!rows.length) {
        elBody.innerHTML = `<tr><td colspan="${1+SUFFIX_ORDER.length}" style="text-align:center;color:#9fb3c8;padding:18px">無資料</td></tr>`;
        elCount.textContent = "0";
        return;
      }
      const html = rows.map(r => {
        const cells = [`<td>${fmt(r.device)}</td>`];
        for (const sfx of SUFFIX_ORDER) cells.push(`<td>${fmt(r[sfx])}</td>`);
        return `<tr>${cells.join("")}</tr>`;
      }).join("");
      elBody.innerHTML = html;
      elCount.textContent = String(rows.length);
    }

    async function refresh() {
      elMsg.textContent = "";
      try {
        const res = await fetch(DEVICES_URL, { headers: { "Accept": "application/json" } });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const json = await res.json();
        renderBody(toRows(json));
        elUpdated.textContent = new Date().toLocaleString();
      } catch (err) {
        elMsg.textContent = "讀取失敗：" + err.message;
      }
    }

    renderHead();
    refresh();
    elBtn.addEventListener('click', refresh);
    setInterval(refresh, REFRESH_MS);
  </script>
</body>
</html>
"""
    return Response(html, mimetype="text/html; charset=utf-8")

@app.get("/health")
def health():
    return jsonify({"ok": True, "ha_base": BASE_URL})

@app.get("/devices")
def devices_view():
    """
    聚合同裝置輸出（方案B：只回 value + last_updated，無 unit）
    Query:
      - query   : 關鍵字（比對 entity_id / friendly_name）
      - prefix  : entity_id 開頭（例 sensor.3drp_）
      - suffix  : 可多個（重複帶或逗號分隔），例：state,cttm_usedwatercontrol,lid_state
      - limit   : 限制輸出的『裝置台數』（預設 DEFAULT_LIMIT）
    """
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
            # device_label = _device_label_from_base(base_wo_suffix)

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
