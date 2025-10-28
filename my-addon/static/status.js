/* ==========================================================
   🧭 狀態面板可調參數區（唯一需要維護的部分）
   ========================================================== */
/**
 * ✅ 裝置名稱
 * MQTT topic 裝置名稱
 */
const DEVICE_NAME   = "testprint";

/**
 * ✅ 欄位設定
 * 由上往下依序顯示，屬性與名稱轉換表格
 */
const COLUMN_CONFIG = [
  { key: "_action",    label: "Action" },
  { key: "_fwversion", label: "FWVersion" },
  { key: "_a",         label: "A" },
  { key: "_al",        label: "AL" },
  { key: "_c",         label: "C" },
  { key: "_cm",        label: "CM" },
  { key: "_dn",        label: "DN" },
  { key: "_fs",        label: "FS" },
  { key: "_he",        label: "HE" },
  { key: "_id",        label: "ID" },
  { key: "_k",         label: "K" },
  { key: "_m",         label: "M" },
  { key: "_p",         label: "P" },
  { key: "_page",      label: "Page" },
  { key: "_tsrm",      label: "TSRM" },
  { key: "_w",         label: "W" },
  { key: "_y",         label: "Y" },
  { key: "_yk",        label: "YK" },
  { key: "_ymov",      label: "Ymov" },
  { key: "_z1",        label: "Z1" },
  { key: "_z2",        label: "Z2" },
];

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
const DEFAULT_PREFIX = `sensor.${DEVICE_NAME}_`;
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
let visibleSet = loadVisibleSet() || new Set(COLUMN_CONFIG.map(c => c.key));

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
    const cells = [`<td>${fmt(r.device)}</td>`];
    for(const col of currentColumns()){
      cells.push(`<td>${fmt(r[col.key])}</td>`);
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
