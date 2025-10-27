# main.py
import logging
import json
import requests
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response

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
# ---------------- 你的原始參數（沿用） ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

with open("/data/options.json", "r", encoding="utf-8") as f:
    options = json.load(f)

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
# ---------------- Flask API ----------------
app = Flask(__name__)

@app.get("/status2")
def status2_page():
    html = r"""
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>列印狀態面板 /status2</title>
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
  .container{max-width:95vw;margin:20px auto;padding:0 8px;}
  .card{
    width:100%;
    background:linear-gradient(180deg,var(--panel),var(--panel2));
    border:1px solid var(--border);
    border-radius:16px;
    box-shadow:var(--shadow);
  }
  .header{padding:18px 18px 0}
  h1{margin:0;font-size:22px}
  .sub{color:var(--muted);font-size:13px;margin-top:6px;word-break:break-all}
  .controls{position:relative;display:flex;gap:10px;align-items:center;padding:14px 18px 18px;flex-wrap:wrap}
  .pill{border:1px solid var(--border);border-radius:999px;padding:6px 10px;font-size:12px;color:var(--muted)}
  .btn{border:1px solid #2b4256;background:linear-gradient(180deg,#15324a,#10273a);color:#d9f1ff;border-radius:10px;padding:8px 12px;cursor:pointer}
  .btn:active{transform:translateY(1px)}
  .table-wrap{border-top:1px solid var(--border);position:relative}
  .scroller{
    max-height:70vh;overflow:auto;overflow-x:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;
  }
  table{
    width:max(1400px,100%);border-collapse:separate;border-spacing:0;table-layout:auto;min-width:100%;
  }
  thead th{
    position:sticky;top:0;background:#0f151c;z-index:2;text-align:left;
    font-size:13px;color:#c7d7ea;padding:10px 12px;
    border-bottom:1px solid var(--border);border-right:1px solid var(--border);
    white-space:nowrap;min-width:120px;
  }
  thead th:first-child,tbody td:first-child{
    position:sticky;left:0;z-index:3;background:linear-gradient(180deg,var(--panel),var(--panel2));
    border-right:1px solid var(--border);min-width:220px;
  }
  tbody td{
    padding:10px 12px;font-size:13px;color:#e6eef8;
    border-bottom:1px solid #17212c;border-right:1px solid #17212c;white-space:nowrap;
  }
  tbody tr:hover td{background:#0f1922}
  .statusbar{display:flex;justify-content:space-between;gap:12px;padding:12px 16px;color: var(--muted);  border-top:1px solid var(--border);background:#0c1218;font-size:12px;border-radius:0 0 16px 16px}
  .mono{font-family:ui-monospace,Menlo,Consolas,monospace}
  .err{color:#ffd1d1}
  .tag{padding:4px 8px;border:1px solid var(--border);border-radius:999px;font-size:12px}
  .tag.live{background:#10273a;color:#d9f1ff;border-color:#2b4256}

  /* 欄位過濾下拉 */
  .filter-pop{
    position:absolute; top:54px; left:18px; width:260px; max-height:340px;
    background:linear-gradient(180deg,var(--panel),var(--panel2));
    border:1px solid var(--border); border-radius:12px; box-shadow:var(--shadow);
    padding:8px; overflow:auto; display:none; z-index:30;
  }
  .filter-pop.show{ display:block; }
  .filter-head{ display:flex; align-items:center; justify-content:space-between; padding:6px 8px; border-bottom:1px solid var(--border); margin-bottom:6px; }
  .filter-row{ display:flex; gap:8px; align-items:center; padding:6px 8px; border-bottom:1px solid #17212c; }
  .filter-row:last-child{ border-bottom:0 }
  .filter-row label{ flex:1; font-size:13px; color:var(--text); cursor:pointer }
  .mini{ font-size:12px; color:var(--muted); }
</style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="header">
        <h1>列印狀態（/status2）</h1>
        <div class="sub">
          資料來源：
          <code id="srcText">/devices?prefix=sensor.testprint_&amp;suffix=_a,_action,_al,_c,_cm,_dn,_fs,_fwversion,_he,_id,_k,_m,_p,_page,_tsrm,_w,_y,_yk,_ymov,_z1,_z2</code>
          （每 60 秒自動刷新）
        </div>
      </div>

      <div class="controls">
        <button id="btnFilter" class="btn">顯示 / 隱藏欄位</button>
        <button id="btnRefresh" class="btn">立即刷新</button>

        <!-- 欄位過濾下拉 -->
        <div id="filterPop" class="filter-pop" role="dialog" aria-label="欄位過濾">
          <div class="filter-head">
            <div class="mini">勾選要顯示的欄位</div>
            <div>
              <button id="btnAllOn" class="btn" style="padding:4px 8px">全選</button>
              <button id="btnAllOff" class="btn" style="padding:4px 8px">全不選</button>
            </div>
          </div>
          <div id="filterList"></div>
        </div>
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
/* ---------- Live API 設定 ---------- */
const DEVICES_URL = "/devices?prefix=sensor.testprint_&suffix=_a,_action,_al,_c,_cm,_dn,_fs,_fwversion,_he,_id,_k,_m,_p,_page,_tsrm,_w,_y,_yk,_ymov,_z1,_z2";

/* ---------- 欄位定義（依 suffix 順序） ---------- */
const FIELD_KEYS = ["_a","_action","_al","_c","_cm","_dn","_fs","_fwversion","_he","_id","_k","_m","_p","_page","_tsrm","_w","_y","_yk","_ymov","_z1","_z2"];

// 給每個欄位一個乾淨的顯示名（可自訂）
const FIELD_LABELS = {
  "_a":"A",
  "_action":"Action",
  "_al":"AL",
  "_c":"C",
  "_cm":"CM",
  "_dn":"DN",
  "_fs":"FS",
  "_fwversion":"FWVersion",
  "_he":"HE",
  "_id":"ID",
  "_k":"K",
  "_m":"M",
  "_p":"P",
  "_page":"Page",
  "_tsrm":"TSRM",
  "_w":"W",
  "_y":"Y",
  "_yk":"YK",
  "_ymov":"Ymov",
  "_z1":"Z1",
  "_z2":"Z2"
};
/* ---------- 偏好持久化 ---------- */
const LS_KEY = "status2_visible_columns_v2";
function loadVisibleSet(){
  try{
    const raw = localStorage.getItem(LS_KEY);
    if(!raw) return null;
    const arr = JSON.parse(raw);
    if(Array.isArray(arr)) return new Set(arr.filter(k=>FIELD_KEYS.includes(k)));
  }catch(_){}
  return null;
}
function saveVisibleSet(set){
  localStorage.setItem(LS_KEY, JSON.stringify([...set]));
}
let visibleSet = loadVisibleSet() || new Set(FIELD_KEYS);

/* ---------- DOM ---------- */
const elHead = document.getElementById('thead');
const elBody = document.getElementById('tbody');
const elCount = document.getElementById('count');
const elUpdated = document.getElementById('updated');
const elMsg = document.getElementById('msg');
const elFilter = document.getElementById('filterPop');
const elFilterList = document.getElementById('filterList');
const REFRESH_MS = 60000;

/* ---------- 工具 ---------- */
function fmt(v){ return (v===null || v===undefined) ? "" : String(v); }
function currentFields(){ return FIELD_KEYS.filter(k => visibleSet.has(k)); }

function renderHead(){
  const cols = ["裝置", ...currentFields().map(k => FIELD_LABELS[k] || k)];
  elHead.innerHTML = cols.map(c => `<th>${c}</th>`).join("");
}

function toRows(payload){
  const rows = [];
  const devices = Array.isArray(payload?.devices) ? payload.devices : [];
  for(const d of devices){
    const id = d?.device_id ?? "";
    const m = d?.metrics ?? {};
    const row = { device: id };
    for(const key of currentFields()){
      row[key] = m[key]?.value ?? "";
    }
    rows.push(row);
  }
  return rows;
}

function renderBody(rows){
  if(!rows.length){
    elBody.innerHTML = `<tr><td colspan="${1+currentFields().length}" style="text-align:center;color:#9fb3c8;padding:18px">無資料</td></tr>`;
    elCount.textContent = "0";
    return;
  }
  elBody.innerHTML = rows.map(r=>{
    const cells = [`<td>${fmt(r.device)}</td>`];
    for(const key of currentFields()) cells.push(`<td>${fmt(r[key])}</td>`);
    return `<tr>${cells.join("")}</tr>`;
  }).join("");
  elCount.textContent = String(rows.length);
}

async function loadLive(){
  const res = await fetch(DEVICES_URL, { headers:{ "Accept":"application/json" }});
  if(!res.ok) throw new Error("HTTP "+res.status);
  return res.json();
}
async function refresh(){
  elMsg.textContent = "";
  try{
    const data = await loadLive();
    renderHead();
    renderBody(toRows(data));
    elUpdated.textContent = new Date().toLocaleString();
  }catch(e){
    elMsg.textContent = "讀取失敗："+e.message;
  }
}

/* ---------- 欄位過濾 UI ---------- */
function rebuildFilterList(){
  elFilterList.innerHTML = FIELD_KEYS.map(k => `
    <div class="filter-row">
      <input id="chk_${k}" type="checkbox" ${visibleSet.has(k) ? "checked":""}
             onchange="toggleField('${k}', this.checked)" />
      <label for="chk_${k}">${FIELD_LABELS[k] || k}</label>
    </div>
  `).join("");
}

window.toggleField = function(k, on){
  if(on) visibleSet.add(k); else visibleSet.delete(k);
  saveVisibleSet(visibleSet);
  refresh();
};

document.getElementById('btnFilter').addEventListener('click', ()=>{
  if(elFilter.classList.contains('show')) { elFilter.classList.remove('show'); return; }
  rebuildFilterList();
  elFilter.classList.add('show');
});
document.addEventListener('click', (e)=>{
  const btn = document.getElementById('btnFilter');
  if(!elFilter.contains(e.target) && e.target !== btn){ elFilter.classList.remove('show'); }
});
document.getElementById('btnAllOn').addEventListener('click', ()=>{
  visibleSet = new Set(FIELD_KEYS); saveVisibleSet(visibleSet); rebuildFilterList(); refresh();
});
document.getElementById('btnAllOff').addEventListener('click', ()=>{
  visibleSet = new Set(); saveVisibleSet(visibleSet); rebuildFilterList(); refresh();
});

/* ---------- 啟動 ---------- */
document.getElementById('btnRefresh').addEventListener('click', refresh);
refresh();
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
