# -*- coding: utf-8 -*-
"""AI 主播试听台 — yachiyo 虚拟主播线的可试听前端。

两条线：
  唱歌  RVC 歌声转换（任意歌 → yachiyo 音色）：参数矩阵 A–F + 两首成品 + 原唱对照
  说话  Qwen3-TTS 克隆音色：参考音色 → 克隆 → v1–v4 微调 → 多语言

音频由既有实验产物整理（22.05 kHz 单声道 96 kbps，唯矩阵/成品用无损源重编码）；
本页只做重放，不改任何参数。
"""
import base64
import json
import os

import streamlit as st
import streamlit.components.v1 as components

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
AUDIO = os.path.join(DATA, "audio")

st.set_page_config(page_title="AI 主播试听台 · yachiyo", page_icon="🎤", layout="wide")


@st.cache_data(show_spinner=False)
def load_manifest():
    with open(os.path.join(DATA, "manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)["groups"]


@st.cache_data(show_spinner=False)
def load_matrix_metrics():
    path = os.path.join(DATA, "rvc_matrix_results.json")
    if not os.path.exists(path):
        return None
    return json.load(open(path, encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_peaks():
    path = os.path.join(DATA, "peaks.json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


@st.cache_data(show_spinner=False)
def audio_b64(name):
    with open(os.path.join(AUDIO, name), "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def fmt_dur(d):
    if d is None:
        return "—"
    m, s = divmod(int(round(d)), 60)
    return f"{m}:{s:02d}" if m else f"{s}s"


# ---------------- shared player building blocks ----------------

def player_html(items, page_id, mode="multi", height=150):
    """items: [{id, file, desc, dur}] — one compact player per item, single-audio playback."""
    payload = []
    for it in items:
        payload.append({
            "id": it["id"], "desc": it["desc"], "dur": it["dur"],
            "b64": audio_b64(it["file"]),
        })
    js = json.dumps(payload, ensure_ascii=False)
    html = PLAYER_TEMPLATE.replace("__PAYLOAD__", js).replace("__PAGEID__", page_id)
    return html, height


PLAYER_TEMPLATE = r"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:#fff; color:#1f2328;
         font:13.5px/1.5 -apple-system,'PingFang SC','Noto Sans SC',sans-serif; }
  .row { display:flex; align-items:center; gap:10px; padding:6px 4px;
         border-bottom:1px solid #eceff3; }
  .row:last-child { border-bottom:none; }
  .row.playing { background:#f2f7ff; border-radius:8px; }
  button.play { width:34px; height:34px; flex:0 0 34px; border-radius:50%;
                border:1px solid #d0d7de; background:#fff; cursor:pointer;
                font-size:12px; line-height:1; color:#1f2328; }
  .mrow { display:flex; align-items:center; gap:8px; padding:2px 4px 8px;
          border-bottom:1px solid #eceff3; }
  .mrow label { font-size:11px; color:#6b7280; white-space:nowrap; }
  .mrow input[type=range] { width:90px; }
  .mrow .val { font-family:'SF Mono',Menlo,monospace; font-size:11px; color:#1f2328;
               min-width:34px; text-align:right; }
  button.play:hover { border-color:#2f81f7; color:#2f81f7; }
  .row.playing button.play { background:#2f81f7; border-color:#2f81f7; color:#fff; }
  .mid { flex:1; min-width:0; }
  .desc { font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .bar { height:4px; border-radius:2px; background:#eceff3; margin-top:5px; overflow:hidden; }
  .bar i { display:block; height:100%; width:0%; background:#2f81f7; }
  .time { flex:0 0 auto; font-family:'SF Mono',Menlo,monospace; font-size:11px;
          color:#6b7280; min-width:64px; text-align:right; }
</style></head><body>
<div class="mrow"><label>主音量（护耳上限 85%）</label>
  <input type="range" id="master" min="0" max="100" value="70">
  <span class="val" id="masterVal">70%</span></div>
<div id="list"></div>
<script>
const ITEMS = __PAYLOAD__;
const MASTER_MAX = 0.85, FADE_S = 0.06;
let ac = null, limiter = null, masterGain = null, masterVal = 0.7;
function ensureCtx() {
  if (ac) return;
  ac = new (window.AudioContext || window.webkitAudioContext)();
  masterGain = ac.createGain(); masterGain.gain.value = masterVal * MASTER_MAX;
  limiter = ac.createDynamicsCompressor();
  limiter.threshold.value = -3; limiter.knee.value = 0; limiter.ratio.value = 20;
  limiter.attack.value = 0.003; limiter.release.value = 0.25;
  masterGain.connect(limiter); limiter.connect(ac.destination);
}
function setMaster(v) {
  masterVal = v;
  const el = document.getElementById('masterVal'); if (el) el.textContent = Math.round(v*100)+'%';
  if (ac && masterGain) { const t = ac.currentTime; masterGain.gain.cancelScheduledValues(t);
    masterGain.gain.setTargetAtTime(masterVal * MASTER_MAX, t, 0.02); }
}
const masterEl = document.getElementById('master');
if (masterEl) masterEl.oninput = () => { ensureCtx();
  if (ac.state === 'suspended') ac.resume(); setMaster(+masterEl.value / 100); };
const el = (t, c) => { const x = document.createElement(t); if (c) x.className = c; return x; };
function fmt(s) { s = Math.max(0, s || 0); const m = Math.floor(s / 60), r = Math.floor(s % 60);
                  return m + ':' + String(r).padStart(2, '0'); }
function b64buf(b64) {
  const bin = atob(b64), n = bin.length, u = new Uint8Array(n);
  for (let i = 0; i < n; i++) u[i] = bin.charCodeAt(i);
  return u.buffer;
}
let current = -1;
const list = document.getElementById('list');
ITEMS.forEach((it, idx) => {
  const row = el('div', 'row'); row.id = 'row' + idx;
  const btn = el('button', 'play'); btn.textContent = '▶';
  const mid = el('div', 'mid');
  const d = el('div', 'desc'); d.textContent = it.desc;
  const bar = el('div', 'bar'); const fill = el('i'); bar.appendChild(fill);
  mid.appendChild(d); mid.appendChild(bar);
  const tm = el('div', 'time'); tm.textContent = it.dur ? ('0:00 / ' + fmt(it.dur)) : '0:00';
  row.appendChild(btn); row.appendChild(mid); row.appendChild(tm);
  list.appendChild(row);

  const au = new Audio();
  let node = null, gnode = null;
  function attach() {
    ensureCtx();
    if (au.__attached) return;
    const url = URL.createObjectURL(new Blob([b64buf(it.b64)], { type: 'audio/mpeg' }));
    au.src = url;
    node = ac.createMediaElementSource(au);
    gnode = ac.createGain(); gnode.gain.value = 1;
    node.connect(gnode); gnode.connect(masterGain);
    au.__attached = true;
  }
  au.preload = 'metadata';
  function tick() {
    if (au.paused) return;
    const dur = au.duration || it.dur || 0;
    fill.style.width = (dur ? (au.currentTime / dur * 100) : 0) + '%';
    tm.textContent = fmt(au.currentTime) + ' / ' + fmt(dur);
    requestAnimationFrame(tick);
  }
  btn.onclick = () => {
    if (current === idx && !au.paused) { au.pause(); return; }
    if (current >= 0 && current !== idx) {
      const prev = window['au' + current];
      if (prev) { prev.pause(); prev.currentTime = 0; }
      const prow = document.getElementById('row' + current);
      if (prow) prow.classList.remove('playing');
    }
    attach();
    const go = (ac.state === 'suspended') ? ac.resume() : Promise.resolve();
    go.then(() => {
      const t = ac.currentTime;
      gnode.gain.cancelScheduledValues(t); gnode.gain.setValueAtTime(0.0001, t);
      gnode.gain.linearRampToValueAtTime(1.0, t + FADE_S);
      current = idx; row.classList.add('playing'); au.currentTime = 0; au.play(); tick();
    });
  };
  au.onended = () => { btn.textContent = '▶'; row.classList.remove('playing'); current = -1;
                       tm.textContent = '0:00 / ' + fmt(au.duration || it.dur); fill.style.width = '0%'; };
  au.onpause = () => {
    btn.textContent = '▶';
    if (ac && gnode) { const t = ac.currentTime;
      gnode.gain.cancelScheduledValues(t); gnode.gain.setValueAtTime(Math.max(0.0001, gnode.gain.value), t);
      gnode.gain.linearRampToValueAtTime(0.0001, t + FADE_S); }
  };
  au.onplay = () => { btn.textContent = '⏸'; };
  window['au' + idx] = au;
});
</script></body></html>
"""


def ab_player_html(matrix_items, page_id, peaks, height=310):
    """A/B comparison player: pick any two matrix variants, snap-start both, shared playhead."""
    payload = [{"id": it["id"], "desc": it["desc"], "dur": it["dur"],
                "peaks": peaks.get(it["id"], []),
                "b64": audio_b64(it["file"])} for it in matrix_items]
    js = json.dumps(payload, ensure_ascii=False)
    html = AB_TEMPLATE.replace("__PAYLOAD__", js).replace("__PAGEID__", page_id)
    return html, height


AB_TEMPLATE = r"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:#fff; color:#1f2328;
         font:13.5px/1.5 -apple-system,'PingFang SC','Noto Sans SC',sans-serif; }
  .pick { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:10px; }
  select { padding:5px 8px; border-radius:8px; border:1px solid #d0d7de; background:#fff;
           font-size:13px; max-width:330px; }
  button.big { padding:6px 16px; border-radius:8px; border:1px solid #2f81f7; color:#fff;
               background:#2f81f7; font-size:13px; cursor:pointer; }
  button.big.alt { background:#fff; color:#2f81f7; }
  .lanes { display:grid; grid-template-columns:1fr; gap:8px; margin-top:4px; }
  .lane { border:1px solid #eceff3; border-radius:10px; padding:8px 10px; }
  .lane .cap { display:flex; justify-content:space-between; font-size:12.5px; margin-bottom:6px; }
  .lane .cap b { font-weight:600; }
  .wave { display:flex; align-items:flex-end; gap:1px; height:44px; }
  .wave i { flex:1; background:#cdd9ea; border-radius:1px; }
  .pos { height:5px; border-radius:3px; background:#eceff3; margin-top:6px; overflow:hidden; }
  .pos i { display:block; height:100%; width:0%; background:#2f81f7; }
  .clock { font-family:'SF Mono',Menlo,monospace; font-size:12px; color:#6b7280; margin-top:8px; }
</style></head><body>
<div class="pick">
  <select id="selA"></select>
  <select id="selB"></select>
  <button class="big" id="play">▶ 同步播放</button>
  <button class="big alt" id="reset">⟲ 归零</button>
  <span class="mrow" style="border:none;padding:0">
    <label>主音量（护耳上限 85%）</label>
    <input type="range" id="master" min="0" max="100" value="70">
    <span class="val" id="masterVal">70%</span>
  </span>
</div>
<div class="lanes">
  <div class="lane"><div class="cap"><b id="capA">A</b><span id="tmA">0:00</span></div>
    <div class="wave" id="waveA"></div><div class="pos"><i id="posA"></i></div></div>
  <div class="lane"><div class="cap"><b id="capB">B</b><span id="tmB">0:00</span></div>
    <div class="wave" id="waveB"></div><div class="pos"><i id="posB"></i></div></div>
</div>
<div class="clock" id="clock">0:00 / 0:00</div>
<script>
const ITEMS = __PAYLOAD__;
const $ = id => document.getElementById(id);
function b64buf(b64) { const bin = atob(b64), n = bin.length, u = new Uint8Array(n);
  for (let i = 0; i < n; i++) u[i] = bin.charCodeAt(i); return u.buffer; }
function fmt(s) { s = Math.max(0, s || 0); const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return m + ':' + String(r).padStart(2, '0'); }
const urlOf = i => URL.createObjectURL(new Blob([b64buf(ITEMS[i].b64)], { type: 'audio/mpeg' }));
const MASTER_MAX = 0.85, FADE_S = 0.06;
const ac = new (window.AudioContext || window.webkitAudioContext)();
const limiter = ac.createDynamicsCompressor();
limiter.threshold.value = -3; limiter.knee.value = 0; limiter.ratio.value = 20;
limiter.attack.value = 0.003; limiter.release.value = 0.25;
const masterGain = ac.createGain(); masterGain.gain.value = 0.7 * MASTER_MAX;
masterGain.connect(limiter); limiter.connect(ac.destination);
let masterVal = 0.7;
function setMaster(v) { masterVal = v; const el = $('masterVal');
  if (el) el.textContent = Math.round(v * 100) + '%';
  const t = ac.currentTime; masterGain.gain.cancelScheduledValues(t);
  masterGain.gain.setTargetAtTime(masterVal * MASTER_MAX, t, 0.02); }
const auA = new Audio(), auB = new Audio();
const srcA = ac.createMediaElementSource(auA), srcB = ac.createMediaElementSource(auB);
const gA = ac.createGain(), gB = ac.createGain(); gA.gain.value = gB.gain.value = 1;
srcA.connect(gA); gA.connect(masterGain); srcB.connect(gB); gB.connect(masterGain);
auA.src = urlOf(0); auB.src = urlOf(1); auA.preload = auB.preload = 'metadata';

ITEMS.forEach((it, i) => {
  for (const [sel, def] of [['selA', i === 0], ['selB', i === 1]]) {
    const o = document.createElement('option'); o.value = i; o.textContent = it.desc;
    $(sel).appendChild(o);
  }
});
$('selA').value = 0; $('selB').value = 1;

function drawWave(canvasId, idx) {
  const host = $(canvasId); host.innerHTML = '';
  const pk = (ITEMS[idx].peaks && ITEMS[idx].peaks.length) ? ITEMS[idx].peaks : null;
  const n = pk ? pk.length : 120;
  for (let k = 0; k < n; k++) {
    const bar = document.createElement('i');
    const v = pk ? pk[k] : 0.25 + 0.2 * Math.abs(Math.sin((k + 1) * 0.7));
    bar.style.height = Math.max(2, Math.round(v * 40)) + 'px';
    host.appendChild(bar);
  }
}
function loadLane(which) {
  const idx = +$(which === 'A' ? 'selA' : 'selB').value;
  const au = which === 'A' ? auA : auB;
  au.src = urlOf(idx); au.currentTime = 0;
  $(which === 'A' ? 'capA' : 'capB').textContent = ITEMS[idx].desc;
  drawWave('wave' + which, idx);
  $(which === 'A' ? 'tmA' : 'tmB').textContent = fmt(ITEMS[idx].dur);
}
$('selA').onchange = () => loadLane('A');
$('selB').onchange = () => loadLane('B');
$('play').onclick = () => {
  if (!auA.paused || !auB.paused) { auA.pause(); auB.pause(); $('play').textContent = '▶ 同步播放'; return; }
  const L = Math.min(auA.duration || 0, auB.duration || 0) || (ITEMS[0].dur || 0);
  if (Math.abs(auA.currentTime - auB.currentTime) > 0.25) { auA.currentTime = 0; auB.currentTime = 0; }
  const go = (ac.state === 'suspended') ? ac.resume() : Promise.resolve();
  go.then(() => {
    const t = ac.currentTime;
    for (const g of [gA, gB]) { g.gain.cancelScheduledValues(t);
      g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(1.0, t + FADE_S); }
    auA.play(); auB.play(); $('play').textContent = '⏸ 暂停';
    tick();
  });
};
const me = $('master');
if (me) me.oninput = () => { if (ac.state === 'suspended') ac.resume(); setMaster(+me.value / 100); };
$('reset').onclick = () => {
  if (ac) { const t = ac.currentTime;
    for (const g of [gA, gB]) { g.gain.cancelScheduledValues(t);
      g.gain.setValueAtTime(Math.max(0.0001, g.gain.value), t);
      g.gain.linearRampToValueAtTime(0.0001, t + FADE_S); } }
  setTimeout(() => { auA.pause(); auB.pause(); auA.currentTime = 0; auB.currentTime = 0;
    gA.gain.value = gB.gain.value = 1;
    $('play').textContent = '▶ 同步播放'; tick(); }, FADE_S * 1000 + 30);
};
function tick() {
  const L = Math.min(auA.duration || 0, auB.duration || 0) || (ITEMS[0].dur || 0);
  const t = Math.max(auA.currentTime || 0, auB.currentTime || 0);
  const p = L ? (t / L * 100) : 0;
  $('posA').style.width = p + '%'; $('posB').style.width = p + '%';
  $('clock').textContent = fmt(t) + ' / ' + fmt(L);
  if (!auA.paused || !auB.paused) requestAnimationFrame(tick);
}
loadLane('A'); loadLane('B'); tick();
</script></body></html>
"""


# ---------------- page ----------------

st.markdown(
    "<style>"
    "h1 { font-size: 1.55rem !important; }"
    ".block-container { padding-top: 1.1rem; padding-bottom: 1rem; max-width: 1150px; }"
    ".stTabs [data-baseweb='tab-list'] { gap: 6px; }"
    "</style>",
    unsafe_allow_html=True,
)

st.title("AI 主播试听台 · yachiyo")
st.caption(
    "B站虚拟主播链路的两段可试听内容：**唱歌**（RVC 歌声转换，任意歌 → yachiyo 音色）与"
    "**说话**（Qwen3-TTS 克隆音色，含参考→克隆→微调→多语言的完整演进）。素材来自既有实验产物，本页只做重放。"
)

groups = load_manifest()
tab_sing, tab_speech = st.tabs(["🎤 唱歌（RVC 歌声转换）", "🗣️ 说话（Qwen3-TTS 克隆）"])

with tab_sing:
    st.subheader("参数矩阵 A–F · 同一段人声、不同 RVC 参数")
    st.caption(
        "同一段 123.5s 人声跑六组参数：**f0 提取器**（rmvpe/pm）、**index_rate**（0/0.3/0.5，检索混合比例）、"
        "**protect**（0.33/0.5，清辅音保护）。指标为与输入人声对比的客观量（F0 相关系数 / 中位误差 / 90 分位误差 / 50cent 内占比）。"
    )
    matrix = groups["sing_matrix"]
    ab_html, ab_h = ab_player_html(matrix, "matrix", load_peaks())
    components.html(ab_html, height=ab_h)

    metrics = load_matrix_metrics()
    if metrics:
        rows = []
        for r in sorted(metrics, key=lambda x: -float(x["f0_corr"])):
            rows.append({
                "组": r["group"],
                "f0 提取": r["f0"],
                "index_rate": r["ir"],
                "protect": r["prot"],
                "F0 相关 ↑": f"{r['f0_corr']:.3f}",
                "中位误差 (cent) ↓": f"{r['f0_med_err_cent']:.0f}",
                "P90 误差 (cent) ↓": f"{r['f0_p90_err_cent']:.0f}",
                "50cent 内占比 ↑": f"{r['frac_50cent']:.3f}",
                "RMS (dB)": f"{r['rms_db']:.1f}",
            })
        st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption(
            "机器侧读数：**F 组（rmvpe · index 0.3 · protect 0.5）F0 相关最高、中位误差 60 cent**；"
            "E（pm 提取）P90 误差最大；D 相关性最低——但这只是客观量，最终请以听感为准（两组间切换听）。"
        )

    st.subheader("成品 · 完整歌与对照段")
    st.caption("两首完整成品（第一首完整歌、perfect、song3 告白气球）+ song3 原曲对照 + 40s cover 段（原唱/yachiyo 转换）。")
    fin = groups["sing_final"]
    fin_html, fin_h = player_html(fin, "final", height=24 + 46 * len(fin))
    components.html(fin_html, height=fin_h)

with tab_speech:
    st.subheader("克隆链 · 从参考音色到微调版本")
    st.caption(
        "参考音色 → Qwen3-TTS 零样本克隆（非流式/流式）→ v1/v2/v3/v4 微调 → 多语言。"
        "全部为既有实验产物，时长与来源见每行。"
    )
    for key, title in [
        ("speech_ref", "参考音色"),
        ("speech_clone", "克隆结果（零样本 / vLLM / 隧道）"),
        ("speech_ft", "微调版本 v1–v4"),
        ("speech_tone", "语调 / 音色候选"),
        ("speech_misc", "其他候选"),
        ("speech_multi", "多语言（中 / 日 / 英）"),
    ]:
        items = groups.get(key) or []
        if not items:
            continue
        st.markdown(f"**{title}**")
        h = 24 + 46 * len(items)
        html, _ = player_html(items, key, height=h)
        components.html(html, height=h)

st.caption(
    "音频由既有产物整理（统一 22.05 kHz 单声道 96 kbps；矩阵与成品用无损源重编码）；"
    "页面只做重放，不改任何参数、不改变任何实验口径。"
)

if __name__ == "__main__":
    pass
