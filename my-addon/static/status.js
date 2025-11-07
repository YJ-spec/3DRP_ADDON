/* ==========================================================
   🧭 狀態面板可調參數區（唯一需要維護的部分）
   ========================================================== */
/**
 * ✅ 裝置名稱
 * MQTT topic 裝置名稱
 */
const DEVICE_NAME   = "ComeTrue";
const LOWER_DEVICE_NAME = DEVICE_NAME.toLowerCase();
/**
 * ✅ 欄位設定與樣式說明
 *
 * 結構設定：
 *   DEFAULT_VISIBLE_KEYS  → 預設欄位格式
 *   COLUMN_CONFIG         → 欄位屬性與名稱對照（由上往下顯示）
 *   COLOR_RULES           → 狀態著色規則
 * 顏色樣式：
 *   .c-ok   { color: #22c55e; font-weight: 500; }   // 綠色：正常
 *   .c-warn { color: #f59e0b; font-weight: 500; }   // 橘色：警告
 *   .c-bad  { color: #ef4444; font-weight: 600; }   // 紅色：錯誤
 *   .c-info { color: #3b82f6; font-weight: 500; }   // 藍色：資訊
 *
*/
const DEFAULT_VISIBLE_KEYS = ["_action", "_dn", "_page","_totalpage","_z1","_model"];
const COLUMN_CONFIG = [
  { key: "_action",    label: "機台當前動作" },
  { key: "_fwversion", label: "固件版本" },
  { key: "_a",         label: "清潔液量" },
  { key: "_al",        label: "校正情況" },
  { key: "_c",         label: "C墨水量" },
  { key: "_cm",        label: "CM頭壽命" },
  { key: "_dn",        label: "上蓋狀態" },
  { key: "_fs",        label: "參數版本" },
  { key: "_he",        label: "墨頭安裝情況" },
  { key: "_id",        label: "ID" },
  { key: "_k",         label: "K墨水量" },
  { key: "_m",         label: "M墨水量" },
  { key: "_p",         label: "癈粉量" },
  { key: "_page",      label: "當前打印頁" },
  { key: "_totalpage", label: "總頁數" },
  { key: "_tsrm",      label: "TSRM" },
  { key: "_w",         label: "W膠水量" },
  { key: "_y",         label: "Y墨水量" },
  { key: "_yk",        label: "YK頭壽命" },
  //{ key: "_ymov",      label: "Ymov" },
  { key: "_z1",        label: "Z1高度" },
  { key: "_z2",        label: "Z2高度" },
  { key: "_swversion", label: "軟體版本" },
  { key: "_model",     label: "機台型號" },
];

const COLOR_RULES = {
  _action: { // 文字比對（全語系）
    // ✅ 正常狀態
    // idle: "c-ok",
    // printing: "c-info",

    // ❌ 異常 / 錯誤狀態（英文）
    "Fast-axis error!": "c-bad",
    "Tsr err": "c-bad",
    "InkJet over voltage!": "c-bad",
    "The upper lid is opened!": "c-bad",
    "InkJet CM temperature incorrect!": "c-bad",
    "InkJet YK temperature incorrect!": "c-bad",
    "Both InkJet temperature incorrect!": "c-bad",
    "Slow-axis error!": "c-bad",
    "Disconnect": "c-bad",

    // ❌ 異常 / 錯誤狀態（繁體中文）
    "快軸移動錯誤": "c-bad",
    "噴頭電壓過高": "c-bad",
    "Upper lid Open": "c-bad",
    "CM過熱": "c-bad",
    "YK過熱": "c-bad",
    "CMYK過熱": "c-bad",
    "X軸錯誤": "c-bad",
    "未連線": "c-bad",

    // ❌ 異常 / 錯誤狀態（簡體中文）
    "快轴移动错误": "c-bad",
    "喷头电压过高": "c-bad",
    // "Upper lid Open": "c-bad",
    "CM过热": "c-bad",
    "YK过热": "c-bad",
    "CMYK过热": "c-bad",
    "X轴错误": "c-bad",
    "未连线": "c-bad"
  },
  // _dn: {
  //   open: "c-warn",
  //   closed: "c-ok"
  // },
  // _p: [     // 數值範圍
  //   { min: 0,   max: 50,  class: "c-ok" },
  //   { min: 51,  max: 80,  class: "c-warn" },
  //   { min: 81,  max: 9999, class: "c-bad" }
  // ],
  // _z1: (v) => {   // 自定義函式
  //   if (v > 200) return "c-bad";
  //   if (v > 100) return "c-warn";
  //   return "c-ok";
  // }

};

/**
 * ✅ 自動刷新間隔（毫秒）
 */
const REFRESH_MS = 60000;

/* ==========================================================
   ✅ API Query 組合
   prefix   = 要查的 entity 開頭
   suffixes = 自動從 COLUMN_CONFIG 取出所有 key
   DEVICES_URL = /devices?prefix=...&suffix=...
   ========================================================== */
const DEFAULT_PREFIX = `sensor.${LOWER_DEVICE_NAME}_`;  // 自動轉成小寫
// const DEFAULT_PREFIX ="sensor.testprint_";
const SUFFIX_LIST = COLUMN_CONFIG.map(c => c.key).join(",");
const DEVICES_URL = `/devices?prefix=${encodeURIComponent(DEFAULT_PREFIX)}&suffix=${encodeURIComponent(SUFFIX_LIST)}`;

// 初始化畫面上顯示資訊
document.getElementById("srcText").textContent = DEVICES_URL;
document.getElementById("refreshSec").textContent = (REFRESH_MS / 1000).toString();

/* ==========================================================
   🧩 偏好設定（欄位顯示儲存）
   ========================================================== */
const LS_KEY = "status2_visible_columns_v3"; // 改版可換 key，避免舊資料衝突

function loadVisibleSet(){
  try{
    const raw = localStorage.getItem(LS_KEY);
    if(!raw) return null;
    const arr = JSON.parse(raw);
    if(Array.isArray(arr)) {
      return new Set(arr.filter(k => COLUMN_CONFIG.some(c => c.key === k)));
    }
  }catch(_){}
  return null;
}

function saveVisibleSet(set){
  localStorage.setItem(LS_KEY, JSON.stringify([...set]));
}

// 預設全部欄位顯示
// let visibleSet = loadVisibleSet() || new Set(COLUMN_CONFIG.map(c => c.key));
let visibleSet = loadVisibleSet() || new Set(DEFAULT_VISIBLE_KEYS);

/* ==========================================================
   🧩 DOM 快取
   ========================================================== */
const elHead = document.getElementById('thead');
const elBody = document.getElementById('tbody');
const elCount = document.getElementById('count');
const elUpdated = document.getElementById('updated');
const elMsg = document.getElementById('msg');
const elFilter = document.getElementById('filterPop');
const elFilterList = document.getElementById('filterList');

/* ==========================================================
   🧩 工具函式
   ========================================================== */
function fmt(v){
  return (v===null || v===undefined) ? "" : String(v);
}

// 目前啟用的欄位（依 COLUMN_CONFIG 順序）
function currentColumns(){
  return COLUMN_CONFIG.filter(col => visibleSet.has(col.key));
}
// 目前啟用的欄位（依 COLOR_RULES 配置）
function getCellClass(colKey, rawValue) {
  const rule = COLOR_RULES[colKey];
  if (!rule || rawValue == null) return "";

  const v = String(rawValue).toLowerCase();

  // 1) 物件：文字比對
  if (typeof rule === "object" && !Array.isArray(rule)) {
    for (const k in rule) {
      if (v === k.toLowerCase()) return rule[k];
    }
  }

  // 2) 陣列：數值範圍 [{min,max,class}, ...]
  if (Array.isArray(rule)) {
    const num = parseFloat(rawValue);
    if (!isNaN(num)) {
      for (const r of rule) {
        if (num >= r.min && num <= r.max) return r.class;
      }
    }
  }

  // 3) 函式：自定義
  if (typeof rule === "function") {
    const res = rule(Number(rawValue));
    if (typeof res === "string") return res;
  }

  return "";
}

/* ==========================================================
   🧩 表格渲染
   ========================================================== */
function renderHead(){
  const cols = ["裝置", ...currentColumns().map(col => col.label)];
  elHead.innerHTML = cols.map(c => `<th>${c}</th>`).join("");
}

function toRows(payload){
  const rows = [];
  const devices = Array.isArray(payload?.devices) ? payload.devices : [];
  for(const d of devices){
    const id = d?.device_id ?? "";
    const m = d?.metrics ?? {};
    const row = { device: id };
    for(const col of currentColumns()){
      row[col.key] = m[col.key]?.value ?? "";
    }
    rows.push(row);
  }
  return rows;
}

function renderBody(rows){
  if(!rows.length){
    elBody.innerHTML = `<tr><td colspan="${1+currentColumns().length}" style="text-align:center;color:#9fb3c8;padding:18px">無資料</td></tr>`;
    elCount.textContent = "0";
    return;
  }

  elBody.innerHTML = rows.map(r=>{
    let deviceName = r.device;
    // 根據 DEVICE_NAME 自動比對小寫形式
    if (deviceName.includes(LOWER_DEVICE_NAME)) {
      deviceName = deviceName.replace(LOWER_DEVICE_NAME, DEVICE_NAME);
    }
    const cells = [`<td>${fmt(deviceName)}</td>`];
    for (const col of currentColumns()) {
      const val = fmt(r[col.key]);
      const cls = getCellClass(col.key, val);
      cells.push(`<td class="${cls}">${val}</td>`);
    }
    return `<tr>${cells.join("")}</tr>`;
  }).join("");

  elCount.textContent = String(rows.length);
}

/* ==========================================================
   🧩 資料請求
   ========================================================== */
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

/* ==========================================================
   🧩 欄位過濾面板
   ========================================================== */
function rebuildFilterList(){
  elFilterList.innerHTML = COLUMN_CONFIG.map(col => `
    <div class="filter-row">
      <input
        id="chk_${col.key}"
        type="checkbox"
        ${visibleSet.has(col.key) ? "checked":""}
        onchange="toggleField('${col.key}', this.checked)" />
      <label for="chk_${col.key}">${col.label}</label>
    </div>
  `).join("");
}

// inline onchange 用
window.toggleField = function(key, on){
  if(on) visibleSet.add(key);
  else   visibleSet.delete(key);
  saveVisibleSet(visibleSet);
  refresh();
};

document.getElementById('btnFilter').addEventListener('click', ()=>{
  if(elFilter.classList.contains('show')) {
    elFilter.classList.remove('show');
    return;
  }
  rebuildFilterList();
  elFilter.classList.add('show');
});

document.addEventListener('click', (e)=>{
  const btn = document.getElementById('btnFilter');
  if(!elFilter.contains(e.target) && e.target !== btn){
    elFilter.classList.remove('show');
  }
});

document.getElementById('btnAllOn').addEventListener('click', ()=>{
  visibleSet = new Set(COLUMN_CONFIG.map(c => c.key));
  saveVisibleSet(visibleSet);
  rebuildFilterList();
  refresh();
});

document.getElementById('btnAllOff').addEventListener('click', ()=>{
  visibleSet = new Set();
  saveVisibleSet(visibleSet);
  rebuildFilterList();
  refresh();
});

/* ==========================================================
   🧩 啟動程序
   ========================================================== */
document.getElementById('btnRefresh').addEventListener('click', refresh);
refresh();
setInterval(refresh, REFRESH_MS);
