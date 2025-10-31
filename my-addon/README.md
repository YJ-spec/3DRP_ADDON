# 3DRP Integration - 安裝與設定流程

本文件說明如何在 Home Assistant 中正確安裝並設定 **3DRP Integration** 插件，  
讓 ComeTrue® 裝置能自動被 Home Assistant 發現並建立感測器與控制項。

安裝步驟概述：
1. 安裝並啟用 Mosquitto broker  
2. 啟用 Home Assistant 的 MQTT 整合  
3. 安裝並設定 3DRP Integration 插件  

---

## 🧩 步驟 1. 安裝並啟用 Mosquitto broker

1. 進入 Home Assistant → **設定 → 附加元件商店**  
2. 搜尋並安裝 **Mosquitto broker**  
3. 安裝完成後，**啟動** 該附加元件  

---

## 🧠 步驟 2. 啟用 Home Assistant 的 MQTT 整合

1. 前往 **設定 → 裝置與服務 → 新增整合**  
2. 搜尋並選擇 **MQTT**  
3. 在連線設定中填入：  
```yaml
logins: []
require_certificate: false
certfile: fullchain.pem
keyfile: privkey.pem
customize:
  active: true
  folder: mosquitto
```
4. 儲存設定  

---

## ⚙️ 步驟 3. 安裝並設定 3DRP Integration 插件

1. 回到 **附加元件商店**  
2. 安裝 **3DRP Integration**
3. 打開插件的「設定」頁面，填入相關 MQTT 參數  
```yaml
mqtt_topics: +/+/data,+/+/control
mqtt_broker: core-mosquitto
mqtt_port: 1883
mqtt_username: test
mqtt_password: test
```
4. 儲存設定  
5. 啟動 **3DRP Integration** 插件  

---

## ✅ 完成！

- ComeTrue® 裝置上線後會自動被 Home Assistant 偵測。  
- 感測值與控制項會自動建立。  
- 新增設備時無需重新設定。  

---
