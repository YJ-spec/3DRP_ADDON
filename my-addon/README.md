# CurieJet Integration - 安裝與設定流程

本文件說明如何在 Home Assistant 中正確安裝與設定 CurieJet Integration 插件，實現裝置自動發現。

- 簡單說明
- 1.HA產生 TOKEN
- 2.HA安裝本插件並設定
- 3.HA安裝mqttbroker
- 4.修改mqttbroker設定active: true
- 5.HA啟用MQTT整合
- 6.重新啟動mqttbroker

---

## 步驟 1. Home Assistant 產生 Long-Lived Access Token

- 進入 Home Assistant 使用者設定（點左下角個人頭像）。
- 滾動到 **Long-Lived Access Tokens** 區塊。
- 點「建立 Token」，輸入名稱。
- 複製生成的 Token，保存好。

---

## 步驟 2. 安裝並設定 CurieJet Integration 插件

- 在 Home Assistant → **設定 → 附加元件商店**。
- 安裝 **CurieJet Integration**。
- 進入插件設定：
  - 填寫剛剛產生的 Token。
  - 設定 MQTT broker（預設是 `core-mosquitto`）。
  - 儲存並啟動插件。

---

## 步驟 3. 安裝 Mosquitto broker

- 在 **附加元件商店**搜尋並安裝 **Mosquitto broker**。
- 安裝完，暫時不要啟動。

---

## 步驟 4. 修改 Mosquitto 設定

- 編輯 Mosquitto broker 的設定，確保包含：

```yaml
logins: []
require_certificate: false
certfile: fullchain.pem
keyfile: privkey.pem
customize:
  active: true
  folder: mosquitto
```

- **注意**：必須 `customize.active: true`，這樣 Mosquitto 才會讀取 `/share/mosquitto/` 資料夾的外部設定。

---

## 步驟 5. 啟用 Home Assistant 的 MQTT 整合

- 到 HA → **設定 → 裝置與服務 → 新增整合**。
- 選擇 **MQTT**。
- 設定連線：
  - 伺服器：`core-mosquitto`
  - 埠號：`1883`
  - 帳號密碼：如果有設定，填入；若無留空。

---

## 步驟 6. 重新啟動 Mosquitto broker

- 回到附加元件頁面，**重新啟動 Mosquitto broker**。
- 讓新的 `customize` 設定生效。

---

# 完成！

- 只要 CurieJet 裝置有上線，會自動出現在 Home Assistant 中。
- 不需要手動搬移任何檔案。

