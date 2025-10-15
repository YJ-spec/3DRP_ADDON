# main.py
import logging
import json
import requests
import os
from flask import Flask, request, jsonify

# ---------------- 你的原始參數（沿用） ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

with open("/data/options.json", "r", encoding="utf-8") as f:
    options = json.load(f)

TOPICS = options.get("mqtt_topics", "+/+/data,+/+/control").split(",")
MQTT_BROKER = options.get("mqtt_broker", "core-mosquitto")
MQTT_PORT = int(options.get("mqtt_port", 1883))
MQTT_USERNAME = options.get("mqtt_username", "")
MQTT_PASSWORD = options.get("mqtt_password", "")
LONG_TOKEN = options.get("HA_LONG_LIVED_TOKEN", "")  # ← 沿用你的命名

HEADERS = {
    "Authorization": f"Bearer {LONG_TOKEN}",
    "Content-Type": "application/json"
}

BASE_URL = options.get("ha_base_url", "http://homeassistant:8123/api").rstrip("/")

# 伺服器設定（可放 options.json 或給預設）
HTTP_HOST = options.get("http_host", "0.0.0.0")
HTTP_PORT = int(options.get("http_port", 8099))
LOG_LEVEL  = options.get("log_level", "INFO").upper()
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

if not LONG_TOKEN:
    logging.warning("HA Long-Lived Token 未設定（/data/options.json 的 HA_LONG_LIVED_TOKEN）。")

# ---------------- 核心：查清單 / 讀欄位 ----------------
def _get_all_states():
    """GET /api/states 取回全部實體狀態。"""
    if not HEADERS.get("Authorization"):
        raise RuntimeError("HA Token 未設定（HEADERS 無 Authorization）")
    url = f"{BASE_URL}/states"
    resp = requests.get(url, headers=HEADERS, timeout=5)
    resp.raise_for_status()
    return resp.json()  # list[dict]

def _match_keyword(entity: dict, kw: str) -> bool:
    """在 entity_id 與 friendly_name 做不分大小寫包含搜尋。"""
    if not kw:
        return True
    kw = kw.lower()
    eid = (entity.get("entity_id") or "").lower()
    name = (entity.get("attributes", {}).get("friendly_name") or "").lower()
    return (kw in eid) or (kw in name)

def _startswith_prefix(entity: dict, prefix: str) -> bool:
    if not prefix:
        return True
    eid = (entity.get("entity_id") or "")
    return eid.startswith(prefix)

def _endswith_suffix(entity: dict, suffix: str) -> bool:
    if not suffix:
        return True
    eid = (entity.get("entity_id") or "")
    return eid.endswith(suffix)

def ha_search_entities(query: str=None, prefix: str=None, suffix: str=None, limit: int=500):
    """
    取得清單（依關鍵字/前綴/後綴篩選）。
    - query: 關鍵字（不分大小寫，比對 entity_id / friendly_name）
    - prefix: entity_id 必須以此字串開頭（例 'sensor.zp2_'）
    - suffix: entity_id 必須以此字串結尾（例 '_p25'）
    - limit: 最大筆數
    回傳：list[dict]
    """
    states = _get_all_states()
    out = []
    for s in states:
        if not _startswith_prefix(s, prefix or ""):
            continue
        if not _endswith_suffix(s, suffix or ""):
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

def ha_read(entity_id: str, field: str="state"):
    """
    讀取單一實體指定欄位。
    field 支援：
      - "state"（預設）
      - "attributes.<key>"（例：attributes.unit_of_measurement）
      - "attr:<key>" 簡寫（例：attr:device_class）
    回傳：欄位值（找不到時回 None）；404 時丟出 LookupError。
    """
    if not entity_id:
        raise ValueError("entity_id 不可為空")
    if not HEADERS.get("Authorization"):
        raise RuntimeError("HA Token 未設定（HEADERS 無 Authorization）")

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

# ---------------- 輕量 Flask API ----------------
app = Flask(__name__)

@app.get("/entities")
def api_entities():
    """
    取得清單（依關鍵字/前綴/後綴）
    Query:
      - query: 關鍵字（不分大小寫，比對 entity_id / friendly_name）
      - prefix: 需符合 entity_id 開頭（例 sensor.zp2_）
      - suffix: 需符合 entity_id 結尾（例 _p25）
      - limit: 最多回傳幾筆（預設 500）
    """
    query  = request.args.get("query", "").strip()
    prefix = request.args.get("prefix", "").strip()
    suffix = request.args.get("suffix", "").strip()
    limit  = int(request.args.get("limit", 500))
    try:
        items = ha_search_entities(query=query, prefix=prefix, suffix=suffix, limit=limit)
        return jsonify({"count": len(items), "items": items})
    except requests.HTTPError as e:
        return jsonify({"error": f"HTTP {e.response.status_code}", "detail": e.response.text[:300]}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/read")
def api_read():
    """
    讀取單一實體的指定欄位
    Query:
      - entity_id: 必填（例 sensor.zp2_xx_xx_p25）
      - field: 預設 state；或 attributes.xxx / attr:xxx
    """
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

if __name__ == "__main__":
    logging.info(f"HA base: {BASE_URL}")
    logging.info(f"HTTP listening on {HTTP_HOST}:{HTTP_PORT}")
    app.run(host=HTTP_HOST, port=HTTP_PORT, debug=False, threaded=True)
