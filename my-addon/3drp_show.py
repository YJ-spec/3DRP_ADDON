# main.py
import logging
import json
import requests
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify

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

def _match_keyword(entity, kw):
    if not kw:
        return True
    kw = kw.lower()
    eid = (entity.get("entity_id") or "").lower()
    name = (entity.get("attributes", {}).get("friendly_name") or "").lower()
    return (kw in eid) or (kw in name)

def _startswith_prefix(entity, prefix):
    return not prefix or (entity.get("entity_id", "").startswith(prefix))

def _endswith_suffix(entity, suffix):
    return not suffix or (entity.get("entity_id", "").endswith(suffix))

def _endswith_any(entity, suffixes):
    """suffixes 為 list；任一符合即通過。空 list 視為不過濾。"""
    if not suffixes:
        return True
    eid = entity.get("entity_id", "")
    return any(eid.endswith(s) for s in suffixes if s)


def ha_search_entities(query: str=None, prefix: str=None, suffix=None, limit: int=500):
    # suffix 可能是 None / str / list
    if suffix is None:
        suffixes = []
    elif isinstance(suffix, str):
        suffixes = [s.strip() for s in suffix.split(",") if s.strip()]
    else:
        # 已是 list
        suffixes = [s.strip() for s in suffix if s and s.strip()]

    states = _get_all_states()
    out = []
    for s in states:
        if not _startswith_prefix(s, prefix or ""):
            continue
        if not _endswith_any(s, suffixes):
            continue
        if not _match_keyword(s, (query or "").strip()):
            continue
        out.append({
            "entity_id": s.get("entity_id"),
            "state": s.get("state"),
            "friendly_name": s.get("attributes", {}).get("friendly_name"),
            "unit": s.get("attributes", {}).get("unit_of_measurement"),
            "last_changed": s.get("last_changed"),
            "last_updated": s.get("last_updated"),
        })
        if len(out) >= limit:
            break
    return out


def ha_read(entity_id, field="state"):
    """讀取單一實體的指定欄位。"""
    url = f"{BASE_URL}/states/{entity_id}"
    resp = requests.get(url, headers=HEADERS, timeout=5)
    if resp.status_code == 404:
        raise LookupError(f"Entity 不存在：{entity_id}")
    resp.raise_for_status()
    ent = resp.json()
    if field in (None, "", "state"):
        return ent.get("state")
    if field.startswith("attributes."):
        key = field.split(".", 1)[1]
        return ent.get("attributes", {}).get(key)
    if field.startswith("attr:"):
        key = field.split(":", 1)[1]
        return ent.get("attributes", {}).get(key)
    return None

def _parse_suffixes_from_request():
    # 支援 ?suffix=a&suffix=b 以及 ?suffix=a,b
    suffix_params = request.args.getlist("suffix")
    suffixes = []
    if suffix_params:
        for s in suffix_params:
            suffixes.extend([x.strip() for x in s.split(",") if x.strip()])
    else:
        # 用預設（允許 DEFAULT_SUFFIX 放逗號清單）
        suffixes = [x.strip() for x in (DEFAULT_SUFFIX or "").split(",") if x.strip()]
    return suffixes

def _eid_matches_suffixes(eid: str, suffixes: list[str]) -> bool:
    if not suffixes:
        return True
    for s in suffixes:
        if not s:
            continue
        # 允許帶或不帶底線的寫法
        if eid.endswith(s) or eid.endswith("_" + s):
            return True
    return False

def _device_label_from_entity_id(eid: str) -> str:
    # sensor.3drp_211242142_state -> 3drp_211242142
    base = eid.split(".", 1)[1] if "." in eid else eid
    if "_" in base:
        device_part = base.rsplit("_", 1)[0]
    else:
        device_part = base
    # 正常化：3drp -> 3DRP，其它維持原樣
    if device_part.startswith("3drp"):
        return "3DRP" + device_part[len("3drp"):]
    return device_part
# ---------------- Flask API ----------------
app = Flask(__name__)

@app.get("/entities")
def api_entities():
    query  = request.args.get("query", DEFAULT_QUERY).strip()
    prefix = request.args.get("prefix", DEFAULT_PREFIX).strip()

    # 同時支援：?suffix=_p25&suffix=_p10&suffix=_p1 以及 ?suffix=_p25,_p10,_p1
    suffix_params = request.args.getlist("suffix")
    suffixes = []
    if suffix_params:
        for s in suffix_params:
            suffixes.extend([x.strip() for x in s.split(",") if x.strip()])
    else:
        # 沒有帶就用預設（也可設成空字串表示不過濾）
        suffixes = [x.strip() for x in (DEFAULT_SUFFIX or "").split(",") if x.strip()]

    limit  = int(request.args.get("limit", DEFAULT_LIMIT))
    try:
        items = ha_search_entities(query=query, prefix=prefix, suffix=suffixes, limit=limit)
        return jsonify({"count": len(items), "items": items})
    except requests.HTTPError as e:
        return jsonify({"error": f"HTTP {e.response.status_code}", "detail": e.response.text[:300]}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/read")
def api_read():
    """讀取單一實體的指定欄位"""
    eid = request.args.get("entity_id", "").strip()
    field = (request.args.get("field", "state") or "state").strip()
    if not eid:
        return jsonify({"error": "missing entity_id"}), 400
    try:
        value = ha_read(eid, field=field)
        return jsonify({"entity_id": eid, "field": field, "value": value})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except requests.HTTPError as e:
        return jsonify({"error": f"HTTP {e.response.status_code}", "detail": e.response.text[:300]}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/health")
def health():
    return jsonify({"ok": True, "ha_base": BASE_URL})

@app.get("/devices")
def devices_view():
    """
    聚合同裝置輸出（方案B：value + last_updated）。
    Query:
      - query: 關鍵字（比對 entity_id / friendly_name）
      - prefix: entity_id 開頭（例 sensor.3drp_）
      - suffix: 可多個（重複帶或逗號分隔），例：state,cttm_usedwatercontrol,lid_state
      - limit: 限制輸出的裝置台數（預設 DEFAULT_LIMIT）
    """
    query  = request.args.get("query", DEFAULT_QUERY).strip()
    prefix = request.args.get("prefix", DEFAULT_PREFIX).strip()
    limit  = int(request.args.get("limit", DEFAULT_LIMIT))
    suffixes = _parse_suffixes_from_request()

    try:
        # 一次取回全部 states，自行過濾（避免多次 HTTP round trips）
        states = _get_all_states()

        devices_map: dict[str, dict] = {}
        for s in states:
            eid = s.get("entity_id") or ""
            if prefix and not eid.startswith(prefix):
                continue
            # 關鍵字（eid 或 friendly_name）
            if query:
                name = (s.get("attributes", {}).get("friendly_name") or "")
                if (query.lower() not in eid.lower()) and (query.lower() not in name.lower()):
                    continue
            # 後綴比對
            if not _eid_matches_suffixes(eid, suffixes):
                continue

            # 解析 device 與 metric 名稱
            base = eid.split(".", 1)[1] if "." in eid else eid
            metric = base.rsplit("_", 1)[-1] if "_" in base else base
            device_label = _device_label_from_entity_id(eid)

            # 建立裝置項
            if device_label not in devices_map:
                devices_map[device_label] = {"device_id": device_label, "metrics": {}}

            devices_map[device_label]["metrics"][metric] = {
                "value": s.get("state"),
                "last_updated": s.get("last_updated"),
            }

        # 轉成 list，限制台數
        devices_list = list(devices_map.values())
        devices_list.sort(key=lambda d: d["device_id"])  # 可換成依最新更新排序
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
