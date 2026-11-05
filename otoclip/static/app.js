"use strict";
const $ = (s) => document.querySelector(s);
const form = $("#form"), urlIn = $("#url"), errEl = $("#err");
const jobsEl = $("#jobs"), libEl = $("#lib"), player = $("#player");
const YT_RE = /https?:\/\/(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be|youtube-nocookie\.com)\/[^\s]+/i;
let knownDone = new Set();
let playing = null;
let pollTimer = null;

const STATUS = {
  queued: "順番待ち",
  downloading: "ダウンロード中",
  converting: "MP3 に変換中",
  done: "完了",
  error: "失敗",
};

function store(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }
function load(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }

function showErr(msg) { errEl.textContent = msg || ""; errEl.hidden = !msg; }
function fmtSize(b) { return b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.round(b / 1024) + " KB"; }
function fmtDate(t) {
  const d = new Date(t * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of kids) if (c != null) e.append(c);
  return e;
}
const fileUrl = (name, dl) => "/files/" + encodeURIComponent(name) + (dl ? "?dl=1" : "");

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error === "unauthorized" ? "接続の認証が切れました。QR コードから開き直してください。" : data.error || `エラー (${r.status})`);
  return data;
}

// ---------- 取得開始 ----------
async function start(text) {
  showErr("");
  const m = (text || "").match(YT_RE);
  const url = m ? m[0] : (text || "").trim();
  if (!url) return showErr("YouTube のリンクを入力してください。");
  $("#go").disabled = true;
  try {
    await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ url, quality: $("#quality").value, playlist: $("#playlist").checked }),
    });
    urlIn.value = "";
    refreshJobs();
  } catch (e) {
    showErr(e.message);
  } finally {
    $("#go").disabled = false;
  }
}

form.addEventListener("submit", (e) => { e.preventDefault(); start(urlIn.value); });

// 貼り付けでは開始しない（Enter か「MP3 を取得」で開始）。
// 「タイトル https://youtu.be/…」のような共有テキストからはリンク部分だけを入力欄に入れる。
urlIn.addEventListener("paste", (e) => {
  const t = (e.clipboardData || window.clipboardData)?.getData("text") || "";
  const m = t.match(YT_RE);
  if (m) { e.preventDefault(); urlIn.value = m[0]; showErr(""); }
});

$("#paste").addEventListener("click", async () => {
  try {
    const t = await navigator.clipboard.readText();
    const m = t.match(YT_RE);
    if (m) { urlIn.value = m[0]; showErr(""); }
    else showErr("クリップボードに YouTube のリンクがありません。");
  } catch (_) {
    showErr("この画面ではボタンから貼り付けできません。入力欄を長押しして「ペースト」してください。");
  }
  urlIn.focus();
});

// 設定を記憶
const q = load("quality"); if (q) $("#quality").value = q;
$("#quality").addEventListener("change", (e) => store("quality", e.target.value));

// ---------- 一覧 ----------
function jobItem(j) {
  const active = j.status === "queued" || j.status === "downloading" || j.status === "converting";
  let meta = STATUS[j.status];
  if (j.status === "downloading" && !j.playlist) meta += ` ${Math.floor(j.progress)}%` + (j.speed ? ` ・ ${j.speed}` : "") + (j.eta ? ` ・ 残り ${j.eta}` : "");
  if (j.playlist && active) meta += ` ${j.item_index}/${j.item_count} 曲目`;
  if (j.message) meta += (meta ? " ・ " : "") + j.message;
  const bar = active ? el("div", { class: "bar" + (j.status === "queued" || (j.status === "converting" && !j.playlist) ? " indet" : "") }, el("i")) : null;
  if (bar) bar.firstChild.style.width = j.progress + "%";

  const acts = el("div", { class: "acts" });
  if (j.status === "done" && j.files.length === 1) {
    acts.append(el("a", { class: "save", href: fileUrl(j.files[0], true), download: j.files[0] }, "保存"));
    acts.append(playBtn(j.files[0]));
  }
  if (!active) acts.append(el("button", { class: "del", onclick: () => api("/api/jobs/" + j.id, { method: "DELETE" }).then(refreshJobs) }, "閉じる"));

  return el("li", { class: "item" },
    el("div", { class: "name" }, j.title || j.url),
    el("div", { class: "meta" + (j.status === "error" ? " bad" : j.status === "done" ? " ok" : "") }, meta),
    bar,
    acts.childNodes.length ? acts : null,
  );
}

function playBtn(name) {
  const b = el("button", {}, playing === name && !player.paused ? "停止" : "再生");
  b.addEventListener("click", () => {
    if (playing === name && !player.paused) { player.pause(); }
    else { player.src = fileUrl(name); player.play(); playing = name; }
    setTimeout(refreshLib, 50);
  });
  return b;
}
player.addEventListener("ended", () => { playing = null; refreshLib(); });

async function refreshJobs() {
  clearTimeout(pollTimer);
  let jobs = [];
  try { jobs = await api("/api/jobs"); } catch (e) { showErr(e.message); }
  $("#jobsSec").hidden = jobs.length === 0;
  jobsEl.replaceChildren(...jobs.map(jobItem));
  let newDone = false;
  for (const j of jobs) if (j.status === "done" && !knownDone.has(j.id)) { knownDone.add(j.id); newDone = true; }
  if (newDone) refreshLib();
  const active = jobs.some((j) => !["done", "error"].includes(j.status));
  pollTimer = setTimeout(refreshJobs, active ? 1000 : 5000);
}

async function refreshLib() {
  let items = [];
  try { items = await api("/api/library"); } catch (_) { return; }
  $("#libEmpty").hidden = items.length > 0;
  libEl.replaceChildren(...items.map((f) => el("li", { class: "item" },
    el("div", { class: "name" }, f.name.replace(/ \[[\w-]{11}\]\.mp3$/, "").replace(/\.mp3$/, "")),
    el("div", { class: "meta" }, `${fmtSize(f.size)} ・ ${fmtDate(f.mtime)}`),
    el("div", { class: "acts" },
      el("a", { class: "save", href: fileUrl(f.name, true), download: f.name }, "保存"),
      playBtn(f.name),
      el("button", {
        class: "del",
        onclick: async () => {
          if (!confirm("このファイルを PC から削除しますか？")) return;
          if (playing === f.name) { player.pause(); playing = null; }
          await fetch(fileUrl(f.name), { method: "DELETE" });
          refreshLib();
        },
      }, "削除"),
    ),
  )));
}

// ---------- 初期化 ----------
async function init() {
  try {
    const info = await api("/api/info");
    $("#ver").textContent = "v" + info.version;
    if (!info.ffmpeg) showErr("ffmpeg が見つからないため MP3 に変換できません。README を確認してください。");
    if (info.is_local) {
      $("#openFolder").hidden = false;
      $("#openFolder").addEventListener("click", () => api("/api/open-folder", { method: "POST" }));
      $("#phone").hidden = false;
      $("#qr").innerHTML = info.qr_svg;
      $("#phoneUrl").textContent = info.phone_url;
    }
  } catch (e) { showErr(e.message); }

  // Android の「共有」やブックマークからの起動: /?url=... または /?text=...
  const p = new URLSearchParams(location.search);
  const shared = p.get("url") || p.get("text");
  if (shared) {
    history.replaceState(null, "", "/");
    start(shared);
  }
  refreshJobs();
  refreshLib();
}
init();

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
