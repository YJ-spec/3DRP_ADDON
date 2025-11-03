import logging
import json
import paho.mqtt.client as mqtt
import requests
import os
import shutil
import time
import threading
import yaml

# ------------------------------------------------------------
# 📦 讀取 Add-on 版本（從 config.yaml）
# ------------------------------------------------------------
def get_addon_version():
    """讀取 add-on 版本號，並加上識別字 'addon'"""
    try:
        with open("/addon/config.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, dict):
                version = data.get("version", "unknown")
                return f"Add-on {version}"
    except Exception as e:
        logging.warning(f"讀取 config.yaml 版本失敗: {e}")
    return "Add-on unknown"

ADDON_VERSION = get_addon_version()

# ------------------------------------------------------------
# 🧾 設定日誌格式
# ------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ------------------------------------------------------------
# ⚙️ 讀取 HA 傳入的設定 (options.json)
# ------------------------------------------------------------
with open("/data/options.json", "r") as f:
    options = json.load(f)

# 從環境變數取得 Long-Lived Token
TOPICS = options.get("mqtt_topics", "+/+/data,+/+/control").split(",")
MQTT_BROKER = options.get("mqtt_broker", "core-mosquitto")
MQTT_PORT = int(options.get("mqtt_port", 1883))
MQTT_USERNAME = options.get("mqtt_username", "")
MQTT_PASSWORD = options.get("mqtt_password", "")

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
BASE_URL = "http://supervisor/core/api"

HEADERS = {
    "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
    "Content-Type": "application/json",
}

# ------------------------------------------------------------
# 🧮 感測單位對照表(for ZS2)
# ------------------------------------------------------------
unit_conditions = {
    "ct": "°C",
    "t": "°C",
    "ch": "%",
    "h": "%",
    "p1": "µg/m³",
    "p25": "µg/m³",
    "p10": "µg/m³",
    "v": "ppm",
    "c": "ppm",
    "ec": "ppm",
    "rset": "rpm",
    "rpm": "rpm"
}

# ------------------------------------------------------------
# 🧩 檢查裝置是否已註冊
# ------------------------------------------------------------
def is_device_registered(device_name, device_mac, candidate_sensors):
    """檢查裝置是否已註冊，只要其中一個代表性實體存在即可"""
    for sensor in candidate_sensors:
        entity_id = f"sensor.{device_name}_{device_mac}_{sensor}"
        url = f"{BASE_URL}/states/{entity_id}"
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code == 200:
                logging.info(f"裝置 {device_name}_{device_mac} 已註冊（找到 {entity_id}）")
                return True
        except Exception as e:
            logging.error(f"查詢 {entity_id} 發生錯誤: {e}")
    return False

# ------------------------------------------------------------
# 🔁 檢查是否需要回傳控制指令(for ZS2)
# ------------------------------------------------------------
def check_and_respond_control(client, topic, message_json):
    parts = topic.split('/')
    if len(parts) < 3:
        return
    device_name, device_mac, message_type = parts

    has_required_payload = (
        message_json.get("Heartbeat") is not None or
        message_json.get("MODEL") is not None
    )

    if has_required_payload:
        control_topic = f"{device_name}/{device_mac}/control"
        control_payload = json.dumps({ "Update": "1" })
        client.publish(control_topic, control_payload)
        logging.info(f"Sent control message to {control_topic}: {control_payload}")

# ------------------------------------------------------------
# 🔗 MQTT 連線成功
# ------------------------------------------------------------
def on_connect(client, userdata, flags, rc):
    logging.info(f"Connected to MQTT broker with result code {rc}")
    for topic in TOPICS:
        client.subscribe(topic)
        logging.info(f"Subscribed to topic: {topic}")

# ------------------------------------------------------------
# 🏗️ 產生 MQTT Discovery Config（數值型）
# ------------------------------------------------------------
def generate_mqtt_discovery_config(device_name, device_mac, sensor_type, sensor_name):
    """ 根據 MQTT 訊息生成 Home Assistant MQTT Discovery 設定 """
    # 生成 topic
    topic = f"{device_name}/{device_mac}/data"

    # 基本 config
    config = {
        "name": sensor_name,
        "state_topic": topic,
        "availability_topic": f"{device_name}/{device_mac}/status",  # ← 新增 LWT 主題
        "payload_available": "online",                 # LWT 上線訊息
        "payload_not_available": "offline",            # LWT 離線訊息
        # "expire_after": 300,
        "value_template": f"{{{{ value_json.{sensor_type}.{sensor_name} }}}}",
        "unique_id": f"{device_name}_{device_mac}_{sensor_name}",
        "state_class": "measurement",
        "force_update": True,
        "device": {
            "identifiers": f"{device_name}_{device_mac}",
            "name": f"{device_name}_{device_mac}",
            "model": device_name,
            # "manufacturer": "CurieJet",
            "sw_version": ADDON_VERSION
        }
    }

    # 如果有單位才加上
    if sensor_name in unit_conditions:
        config["unit_of_measurement"] = unit_conditions[sensor_name]

    return config

# ------------------------------------------------------------
# 🏗️ 產生 MQTT Discovery Config（文字型）
# ------------------------------------------------------------
def generate_mqtt_discovery_textconfig(device_name, device_mac, sensor_type, sensor_name):
    """ 根據 MQTT 訊息生成 Home Assistant MQTT Discovery 設定 """
    # 生成 topic
    topic = f"{device_name}/{device_mac}/data"

    # 基本 config
    config = {
        "name": sensor_name,
        "state_topic": topic,
        "availability_topic": f"{device_name}/{device_mac}/status",  # ← 新增 LWT 主題
        "payload_available": "online",                 # LWT 上線訊息
        "payload_not_available": "offline",            # LWT 離線訊息
        # "expire_after": 300,
        "value_template": f"{{{{ value_json.{sensor_type}.{sensor_name} }}}}",
        "unique_id": f"{device_name}_{device_mac}_{sensor_name}",
        "device": {
            "identifiers": f"{device_name}_{device_mac}",
            "name": f"{device_name}_{device_mac}",
            "model": device_name,
            # "manufacturer": "CurieJet",
            "sw_version": ADDON_VERSION
        }
    }
    
    # 如果有單位才加上
    if sensor_name in unit_conditions:
        config["unit_of_measurement"] = unit_conditions[sensor_name]

    return config

# ------------------------------------------------------------
# 🔔 延遲補發 Online 狀態
# ------------------------------------------------------------
def delayed_online_publish(client, device_name, device_mac):
    status_topic = f"{device_name}/{device_mac}/status"
    time.sleep(1)
    client.publish(status_topic, "online", retain=False)
    logging.info(f"補發 online 狀態到 {status_topic}")
    time.sleep(3)
    client.publish(status_topic, "online", retain=False)
    logging.info(f"再次補發 online 狀態到 {status_topic}")

# ------------------------------------------------------------
# 📨 處理 MQTT 訊息
# ------------------------------------------------------------
def on_message(client, userdata, msg):
    payload = msg.payload.decode()
    logging.info(f"Received message on {msg.topic}: {payload}")

    try:
        # 先解析 JSON
        message_json = json.loads(payload)
        
        # 自動回應
        check_and_respond_control(client, msg.topic, message_json)
        
        # 提取 deviceName 和 deviceMac
        topic_parts = msg.topic.split('/')
        if len(topic_parts) < 3:
            logging.warning(f"Invalid topic format: {msg.topic}")
            return
        device_name = topic_parts[0]
        device_mac = topic_parts[1]
		
        # 準備感測器名稱列表
        candidate_sensors = (
                list(message_json.get("data", {}).keys()) +
                list(message_json.get("data1", {}).keys()) +
                list(message_json.get("textdata", {}).keys())
            )
        # candidate_sensors = list(message_json.get("data", {}).keys()) + list(message_json.get("data1", {}).keys() + list(message_json.get("textdata", {}).keys())
        # 裝置已註冊，跳過 discovery 設定
        if is_device_registered(device_name, device_mac, candidate_sensors):
            return  
            
        if not device_name or not device_mac:
            logging.warning(f"Missing deviceName or deviceMac in message: {payload}")
            return
        
        # 生成對應的 MQTT Discovery 配置
        discovery_configs = []
        
        # 處理 data 欄位的感測器
        data_sensors = message_json.get("data", {})
        for sensor, value in data_sensors.items():
            config = generate_mqtt_discovery_config(device_name, device_mac, "data", sensor)
            discovery_configs.append(config)

        # 處理 data1 欄位的感測器
        data1_sensors = message_json.get("data1", {})
        for sensor, value in data1_sensors.items():
            config = generate_mqtt_discovery_config(device_name, device_mac, "data1", sensor)
            discovery_configs.append(config)

        # 處理 textdata 欄位的感測器
        data1_sensors = message_json.get("textdata", {})
        for sensor, value in data1_sensors.items():
            config = generate_mqtt_discovery_textconfig(device_name, device_mac, "textdata", sensor)
            discovery_configs.append(config)

        # 推送 MQTT Discovery 配置到 HA
        for config in discovery_configs:
            discovery_topic = f"homeassistant/sensor/{device_name}_{device_mac}_{config['name']}/config"
            mqtt_payload = json.dumps(config, indent=2)
            client.publish(discovery_topic, mqtt_payload, retain=True)
            logging.info(f"Published discovery config to {discovery_topic}")
        
        # 在 on_message() 裡這樣改：
        threading.Thread(
            target=delayed_online_publish,
            args=(client, device_name, device_mac),
            daemon=True
        ).start()

    except json.JSONDecodeError:
        logging.error(f"Failed to decode payload: {payload}")
    except Exception as e:
        logging.error(f"Error processing message: {e}")

# ------------------------------------------------------------
# 🧱 複製 MQTT 橋接設定檔(for 中控橋接觀察數據 預設路徑192.168.51.8)
# ------------------------------------------------------------
def create_mqtt_bridge_conf():
    """ 複製 MQTT 桥接配置文件到目标目录 """
    source_file = '/external_bridge.conf'  # 源文件路徑
    target_directory = '/share/mosquitto/'  # 目標目錄路徑

    try:
        # 確保目標目錄存在，如果不存在就創建
        os.makedirs(target_directory, exist_ok=True)
        
        # 複製文件
        shutil.copy(source_file, target_directory)
        
        # 記錄成功訊息
        logging.info(f"File {source_file} has been copied to {target_directory}")
    except Exception as e:
        # 錯誤處理，記錄錯誤訊息
        logging.error(f"Error copying file {source_file} to {target_directory}: {e}")

# ------------------------------------------------------------
# 🚀 主程式
# ------------------------------------------------------------
def main():
    logging.info("Add-on started")

    create_mqtt_bridge_conf()

    client = mqtt.Client()

    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()  # 持續執行直到 Add-on 被 HA 關閉

if __name__ == "__main__":
    main()
