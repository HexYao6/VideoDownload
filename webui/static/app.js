/* VideoDownload WebUI —— 原生 JS，无前端框架依赖 */

const app = document.getElementById('app');
let pollTimer = null;

/* ---------------- 工具 ---------------- */

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && body.error) msg = body.error;
    } catch (_) { /* 忽略非 JSON 响应 */ }
    throw new Error(msg);
  }
  return res.json();
}

function esc(text) {
  return String(text == null ? '' : text).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function fmtDuration(seconds) {
  if (typeof seconds !== 'number' || !isFinite(seconds)) return '';
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

function fmtBytes(n) {
  if (!n) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function upInitial(name) {
  return (name || '?').trim().slice(0, 1).toUpperCase();
}

/* 清晰度徽章：优先显示 1080P60 这类标签，完整信息放进 title */
function qualityBadge(v) {
  if (!v.quality && !v.resolution) return '';
  const tip = [v.resolution, v.codec, v.fps ? v.fps + 'fps' : '']
    .filter(Boolean).join(' · ');
  const label = v.quality || v.resolution;
  return `<span class="badge" title="${esc(tip)}">${esc(label)}</span>`;
}

function clearPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

/* ---------------- 视图：up主列表（一级页面） ---------------- */

async function renderLibrary() {
  app.innerHTML = '<div class="loading">加载中…</div>';
  let data;
  try {
    data = await api('/api/library');
  } catch (err) {
    app.innerHTML = `<div class="empty"><div class="big">⚠️</div>加载失败：${esc(err.message)}</div>`;
    return;
  }

  const uploaders = data.uploaders || [];
  if (!uploaders.length) {
    app.innerHTML = `
      <div class="empty">
        <div class="big">🎬</div>
        <p>下载库里还没有视频。</p>
        <p><a class="btn-link" href="/download">去下载一个 →</a></p>
      </div>`;
    return;
  }

  const total = uploaders.reduce((sum, u) => sum + u.videoCount, 0);
  app.innerHTML = `
    <div class="page-head">
      <h1>视频库</h1>
      <span class="sub">${uploaders.length} 位 up 主 · ${total} 个视频</span>
    </div>
    <div class="grid">
      ${uploaders.map((u) => `
        <a class="card up-card" href="/u/${encodeURIComponent(u.name)}">
          <div class="card-body">
            <div class="up-head">
              <div class="up-avatar">${esc(upInitial(u.name))}</div>
              <div>
                <div class="up-name">${esc(u.name)}</div>
                <div class="up-count">${u.videoCount} 个视频</div>
              </div>
            </div>
          </div>
        </a>`).join('')}
    </div>`;
}

/* ---------------- 视图：up主详情（视频列表） ---------------- */

async function renderUploader(name) {
  app.innerHTML = '<div class="loading">加载中…</div>';
  let data;
  try {
    data = await api(`/api/uploaders/${encodeURIComponent(name)}`);
  } catch (err) {
    app.innerHTML = `
      <div class="empty">
        <div class="big">🔍</div>
        <p>${esc(err.message)}</p>
        <p><a class="btn-link" href="/">← 返回视频库</a></p>
      </div>`;
    return;
  }

  const videos = data.videos || [];
  app.innerHTML = `
    <div class="page-head">
      <a class="back" href="/">← 视频库</a>
      <h1>${esc(data.name)}</h1>
      <span class="sub">${videos.length} 个视频${data.uid ? ' · uid ' + esc(data.uid) : ''}</span>
    </div>
    ${videos.length ? `<div class="grid">${videos.map(videoCard).join('')}</div>`
      : '<div class="empty"><div class="big">📭</div>该 up 主下还没有视频</div>'}`;
}

function videoCard(v) {
  const dur = fmtDuration(v.duration);
  const cover = v.hasCover
    ? `<img src="/media/cover/${encodeURIComponent(v.bvid)}" alt="${esc(v.title)}" loading="lazy">`
    : '<div class="ph">🎞️</div>';
  return `
    <a class="card" href="/v/${encodeURIComponent(v.bvid)}">
      <div class="thumb">
        ${cover}
        ${dur ? `<span class="dur">${dur}</span>` : ''}
      </div>
      <div class="card-body">
        <div class="card-title">${esc(v.title)}</div>
        ${v.description ? `<div class="card-desc">${esc(v.description)}</div>` : ''}
        <div class="card-meta">
          ${qualityBadge(v)}
          ${v.updatedAt ? `<span class="meta-time">${esc(v.updatedAt)}</span>` : ''}
          ${v.hasVideo ? '' : ' <span style="color:var(--err)">（无视频文件）</span>'}
        </div>
      </div>
    </a>`;
}

/* ---------------- 视图：播放页 ---------------- */

async function renderVideo(bvid) {
  app.innerHTML = '<div class="loading">加载中…</div>';
  let data;
  try {
    data = await api(`/api/videos/${encodeURIComponent(bvid)}`);
  } catch (err) {
    app.innerHTML = `
      <div class="empty">
        <div class="big">🔍</div>
        <p>${esc(err.message)}</p>
        <p><a class="btn-link" href="/">← 返回视频库</a></p>
      </div>`;
    return;
  }

  const dur = fmtDuration(data.duration);
  app.innerHTML = `
    <div class="page-head">
      <a class="back" href="/u/${encodeURIComponent(data.uploader.name)}">← ${esc(data.uploader.name)}</a>
    </div>
    <div class="player-wrap">
      <video controls preload="metadata"
             poster="/media/cover/${encodeURIComponent(data.bvid)}"
             src="/media/video/${encodeURIComponent(data.bvid)}"></video>
    </div>
    <h2 class="video-title">${esc(data.title)}</h2>
    <div class="video-meta">
      ${qualityBadge(data)}
      ${esc(data.bvid)}${dur ? ' · ' + dur : ''}${data.updatedAt ? ' · ' + esc(data.updatedAt) : ''}
    </div>
    <div class="video-desc">
      <div class="desc-head">视频简介</div>
      ${data.description ? esc(data.description) : '<span style="color:var(--muted)">暂无简介</span>'}
    </div>`;
}

/* ---------------- 视图：下载页 ---------------- */

function parseBvids(text) {
  /* 支持空格 / 逗号 / 换行 / 分号分隔的多个 BV 号 */
  return String(text || '')
    .split(/[\s,;，、]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function renderDownload() {
  app.innerHTML = `
    <div class="page-head"><h1>下载视频</h1><span class="sub">可一次提交多个，支持并行下载</span></div>
    <div class="panel">
      <form class="download-form" id="download-form">
        <input type="text" id="bvid-input" placeholder="BV1dfJk6hEjX（可用空格/逗号分隔多个）"
               autocomplete="off" spellcheck="false">
        <button class="primary" type="submit" id="download-btn">开始下载</button>
      </form>

      <div class="pick-row">
        <select id="pick-select">
          <option value="">— 从已有视频库中选择 —</option>
        </select>
        <button class="ghost" type="button" id="pick-btn">加入队列</button>
      </div>

      <p class="hint">下载会请求 B 站接口，风控较强时可能需要重试若干次，请耐心等待。</p>
      <div id="download-status"></div>
    </div>

    <div class="page-head" style="margin-top:28px">
      <h1 style="font-size:18px">下载队列</h1>
      <span class="sub" id="queue-summary"></span>
    </div>
    <div id="task-list" class="task-list">
      <div class="loading">加载中…</div>
    </div>`;

  const form = document.getElementById('download-form');
  const input = document.getElementById('bvid-input');
  const button = document.getElementById('download-btn');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const bvids = parseBvids(input.value);
    if (!bvids.length) { input.focus(); return; }
    await submitDownloads(bvids);
    input.value = '';
  });

  document.getElementById('pick-btn').addEventListener('click', async () => {
    const bvid = document.getElementById('pick-select').value;
    if (!bvid) return;
    await submitDownloads([bvid]);
  });

  // 下拉框内容来自视频库，方便重新下载（例如换了 cookie 后想要更高画质）
  loadPickerOptions();
  refreshTasks();
  startTaskPolling();
}

async function loadPickerOptions() {
  const select = document.getElementById('pick-select');
  if (!select) return;
  try {
    const data = await api('/api/library');
    const groups = data.uploaders || [];
    let html = '<option value="">— 从已有视频库中选择 —</option>';
    for (const u of groups) {
      const videos = u.videos || [];
      if (!videos.length) continue;
      html += `<optgroup label="${esc(u.name)}">`;
      for (const v of videos) {
        const tag = v.quality ? ` · ${v.quality}` : '';
        html += `<option value="${esc(v.bvid)}">${esc(v.title.slice(0, 40))}${esc(tag)}</option>`;
      }
      html += '</optgroup>';
    }
    select.innerHTML = html;
  } catch (err) {
    select.innerHTML = '<option value="">（视频库加载失败）</option>';
  }
}

async function submitDownloads(bvids) {
  const button = document.getElementById('download-btn');
  const box = document.getElementById('download-status');
  if (button) button.disabled = true;
  if (box) box.innerHTML = `<div class="notice">正在提交 ${bvids.length} 个下载任务…</div>`;

  try {
    const result = await api('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bvids }),
    });
    if (box) {
      const invalid = result.invalid || [];
      box.innerHTML = invalid.length
        ? `<div class="notice err">已忽略无效 BV 号：${esc(invalid.join(', '))}</div>`
        : `<div class="notice">已加入队列：${esc(bvids.join(', '))}</div>`;
    }
    await refreshTasks();
  } catch (err) {
    if (box) box.innerHTML = `<div class="notice err">提交失败：${esc(err.message)}</div>`;
  } finally {
    if (button) button.disabled = false;
  }
}

async function refreshTasks() {
  const list = document.getElementById('task-list');
  if (!list) return;
  let tasks;
  try {
    const data = await api('/api/downloads');
    tasks = data.tasks || [];
  } catch (err) {
    list.innerHTML = `<div class="notice err">加载队列失败：${esc(err.message)}</div>`;
    return;
  }

  const summary = document.getElementById('queue-summary');
  if (summary) {
    const running = tasks.filter((t) => t.status === 'running' || t.status === 'pending').length;
    summary.textContent = tasks.length
      ? `${tasks.length} 个任务 · ${running} 个进行中`
      : '';
  }

  if (!tasks.length) {
    list.innerHTML = '<div class="empty small"><div class="big">📭</div>队列里还没有任务</div>';
    return;
  }
  list.innerHTML = tasks.map(taskRow).join('');
}

function taskRow(t) {
  const pct = Math.max(0, Math.min(100, t.percent || 0));
  const running = t.status === 'running' || t.status === 'pending';
  const phase = t.phase || '';
  const parts = [];
  if (t.total) parts.push(`${fmtBytes(t.downloaded)} / ${fmtBytes(t.total)}`);
  if (t.speed) parts.push(`${fmtBytes(t.speed)}/s`);
  if (t.eta != null && t.eta >= 0) parts.push(`剩余 ${fmtEta(t.eta)}`);

  const link = t.status === 'success'
    ? `<a class="btn-link" href="/v/${encodeURIComponent(t.bvid)}">前往播放页 →</a>`
    : '';

  const err = t.error ? `<div class="task-err">${esc(t.error)}</div>` : '';

  return `
    <div class="task ${esc(t.status)}">
      <div class="task-head">
        <span class="dot ${esc(t.status)}"></span>
        <span class="task-title">${esc(t.title || t.bvid)}</span>
        <span class="task-bvid">${esc(t.bvid)}</span>
        ${t.quality ? `<span class="badge">${esc(t.quality)}</span>` : ''}
        ${t.uploader ? `<span class="task-up">${esc(t.uploader)}</span>` : ''}
        <span class="task-phase">${esc(phase)}</span>
      </div>
      <div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div>
      <div class="task-foot">
        <span>${pct.toFixed(1)}%</span>
        <span class="task-detail">${esc(parts.join(' · '))}</span>
        ${link}
      </div>
      ${err}
    </div>`;
}

function fmtEta(seconds) {
  const s = Math.round(seconds);
  if (s < 60) return `${s} 秒`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} 分 ${s % 60} 秒`;
  return `${Math.floor(m / 60)} 小时 ${m % 60} 分`;
}

function startTaskPolling() {
  clearPoll();
  pollTimer = setInterval(() => {
    if (!document.getElementById('task-list')) { clearPoll(); return; }
    refreshTasks();
  }, 1200);
}

/* ---------------- 路由 ---------------- */

function route() {
  clearPoll();
  const path = location.pathname;

  document.querySelectorAll('.nav a').forEach((el) => {
    el.classList.toggle('active',
      el.dataset.route === 'download' ? path === '/download' : path === '/');
  });

  if (path === '/download') { renderDownload(); return; }

  const u = path.match(/^\/u\/([^/]+)\/?$/);
  if (u) { renderUploader(decodeURIComponent(u[1])); return; }

  const v = path.match(/^\/v\/([^/]+)\/?$/);
  if (v) { renderVideo(decodeURIComponent(v[1])); return; }

  renderLibrary();
}

document.addEventListener('click', (event) => {
  const link = event.target.closest('a');
  if (!link) return;
  const href = link.getAttribute('href');
  if (!href || !href.startsWith('/')) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey) return;
  event.preventDefault();
  history.pushState({}, '', href);
  route();
});

window.addEventListener('popstate', route);

document.getElementById('refresh-btn').addEventListener('click', () => route());

route();
