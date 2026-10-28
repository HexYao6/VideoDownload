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
          ${v.updatedAt ? esc(v.updatedAt) : ''}
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
      ${esc(data.bvid)}${dur ? ' · ' + dur : ''}${data.updatedAt ? ' · ' + esc(data.updatedAt) : ''}
    </div>
    <div class="video-desc">
      <div class="desc-head">视频简介</div>
      ${data.description ? esc(data.description) : '<span style="color:var(--muted)">暂无简介</span>'}
    </div>`;
}

/* ---------------- 视图：下载页 ---------------- */

function renderDownload() {
  app.innerHTML = `
    <div class="page-head"><h1>下载视频</h1><span class="sub">输入 B 站 BV 号</span></div>
    <div class="panel">
      <form class="download-form" id="download-form">
        <input type="text" id="bvid-input" placeholder="BV1dfJk6hEjX" autocomplete="off" spellcheck="false">
        <button class="primary" type="submit" id="download-btn">开始下载</button>
      </form>
      <p class="hint">下载会请求 B 站接口，风控较强时可能需要重试若干次，请耐心等待。</p>
      <div id="download-status"></div>
    </div>`;

  const form = document.getElementById('download-form');
  const input = document.getElementById('bvid-input');
  const button = document.getElementById('download-btn');
  const statusBox = document.getElementById('download-status');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const bvid = input.value.trim();
    if (!bvid) return;

    clearPoll();
    button.disabled = true;
    statusBox.innerHTML = `
      <div class="status">
        <div class="status-bar"><span class="dot running"></span><span>正在提交…</span></div>
        <pre class="log"></pre>
      </div>`;

    let task;
    try {
      task = await api('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bvid }),
      });
    } catch (err) {
      button.disabled = false;
      statusBox.innerHTML = `
        <div class="status">
          <div class="status-bar"><span class="dot failed"></span><span>提交失败</span></div>
          <pre class="log"><span class="err">${esc(err.message)}</span></pre>
        </div>`;
      return;
    }

    button.disabled = false;
    pollTask(task.taskId, 0);
  });
}

function pollTask(taskId, offset) {
  clearPoll();
  const statusBox = document.getElementById('download-status');
  if (!statusBox) return;

  pollTimer = setInterval(async () => {
    let task;
    try {
      task = await api(`/api/download/${taskId}?offset=${offset}`);
    } catch (err) {
      clearPoll();
      statusBox.innerHTML = `
        <div class="status">
          <div class="status-bar"><span class="dot failed"></span><span>查询失败</span></div>
          <pre class="log"><span class="err">${esc(err.message)}</span></pre>
        </div>`;
      return;
    }

    offset = task.logOffset;
    const label = {
      pending: '排队中', running: '下载中', success: '下载完成', failed: '下载失败',
    }[task.status] || task.status;

    const logHtml = (task.logs || []).map((line) => {
      const bad = /失败|ERROR|error|异常/.test(line);
      return bad ? `<span class="err">${esc(line)}</span>` : esc(line);
    }).join('\n');

    const done = task.status === 'success' || task.status === 'failed';
    const link = task.status === 'success'
      ? `<div style="padding:0 16px 14px"><a class="btn-link" href="/v/${encodeURIComponent(task.bvid)}">→ 前往播放页</a></div>`
      : '';

    statusBox.innerHTML = `
      <div class="status">
        <div class="status-bar">
          <span class="dot ${esc(task.status)}"></span>
          <span>${esc(label)} · ${esc(task.bvid)}</span>
        </div>
        <pre class="log" id="log-box">${logHtml}</pre>
        ${link}
      </div>`;

    const logBox = document.getElementById('log-box');
    if (logBox) logBox.scrollTop = logBox.scrollHeight;

    if (done) {
      clearPoll();
      if (task.error) {
        statusBox.innerHTML = statusBox.innerHTML.replace(
          '</pre>', `<span class="err">${esc(task.error)}</span></pre>`);
      }
    }
  }, 1500);
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
