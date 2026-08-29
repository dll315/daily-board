/* 每日看板前端逻辑 */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function getToken() { return localStorage.getItem('db_token') || ''; }
function setToken(t) { t ? localStorage.setItem('db_token', t) : localStorage.removeItem('db_token'); }

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (getToken()) headers['Authorization'] = 'Bearer ' + getToken();
  const res = await fetch(path, {
    method: opts.method || 'GET',
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) {
    if (res.status === 401 && path.startsWith('/api/admin')) {
      setToken('');
      updateAdminUi();
    }
    throw new Error((data && data.error) || ('请求失败 (' + res.status + ')'));
  }
  return data;
}

/* ---------- Toast ---------- */
let toastTimer = null;
function toast(msg, type) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast show ' + (type || '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = 'toast ' + (type || ''); }, 2800);
}

/* ---------- 顶栏日期 ---------- */
function renderDate() {
  const d = new Date();
  const weeks = ['日', '一', '二', '三', '四', '五', '六'];
  $('#dateText').textContent = d.getFullYear() + '年' + (d.getMonth() + 1) + '月' + d.getDate() + '日 · 星期' + weeks[d.getDay()];
}

/* ---------- 古诗 ---------- */
function renderPoem(p) {
  $('#poemBadge').textContent = p.source === 'local' ? '本地精选' : '今日诗词';
  const by = [p.author, p.dynasty].filter(Boolean).join(' · ');
  let html;
  if (p.lines && p.lines.length) {
    html = '<div class="poem-lines">' + p.lines.map((l) => '<p>' + esc(l) + '</p>').join('') + '</div>';
  } else {
    html = '<blockquote class="poem-quote">“' + esc(p.content) + '”</blockquote>';
  }
  html += '<div class="poem-meta">' + (p.origin ? '《' + esc(p.origin) + '》' : '') +
    (by ? '<span>' + esc(by) + '</span>' : '') + '</div>';
  $('#poemBody').innerHTML = html;
}

async function loadPoem(refresh) {
  const btn = $('#btnPoemRefresh');
  btn.disabled = true;
  try {
    renderPoem(await api('/api/poem' + (refresh ? '?refresh=1' : '')));
  } catch (e) {
    $('#poemBody').innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
  } finally {
    btn.disabled = false;
  }
}

/* ---------- 科技简报 ---------- */
function mdLite(md) {
  const lines = String(md).split(/\n/);
  let html = '', inList = false;
  for (let line of lines) {
    line = esc(line.trim()).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    if (/^- /.test(line)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += '<li>' + line.slice(2) + '</li>';
    } else {
      if (inList) { html += '</ul>'; inList = false; }
      if (!line) continue;
      if (/^#+ /.test(line)) html += '<h3>' + line.replace(/^#+ /, '') + '</h3>';
      else if (/^> /.test(line)) html += '<p style="color:var(--muted);font-size:12.5px">' + line.slice(2) + '</p>';
      else html += '<p>' + line + '</p>';
    }
  }
  if (inList) html += '</ul>';
  return html;
}

function renderBriefing(b) {
  const srcCount = b.sources ? b.sources.split('、').length : 0;
  const label = b.source === 'ai' ? 'AI 生成' : (b.source === 'news' ? (srcCount > 1 ? '聚合 ' + srcCount + ' 源' : '新闻源') : '暂无');
  $('#briefingBadge').textContent = label + (b.updatedAt ? ' · ' + b.updatedAt + ' 更新' : '');
  const body = $('#briefingBody');
  if (b.source === 'none') {
    body.innerHTML = '<div class="empty">' + esc(b.note || '暂无数据') + '</div>';
    return;
  }
  if (b.markdown) {
    body.innerHTML = mdLite(b.markdown);
  } else if (b.items && b.items.length) {
    const TAG_CLASS = { '60s日报': 'tag-daily', '微博热搜': 'tag-weibo', '头条热榜': 'tag-toutiao', '抖音热点': 'tag-douyin' };
    body.innerHTML = '<ol class="news-list">' + b.items.map((i) => {
      if (i && typeof i === 'object') {
        const cls = TAG_CLASS[i.s] || '';
        return '<li><i class="news-tag ' + cls + '">' + esc(i.s) + '</i>' + esc(i.t) + '</li>';
      }
      return '<li>' + esc(i) + '</li>';
    }).join('') + '</ol>';
  } else {
    body.innerHTML = '<div class="empty">今日暂无新闻数据</div>';
  }
  if (b.note) body.innerHTML += '<p class="briefing-note">⚠ ' + esc(b.note) + '</p>';
}

async function loadBriefing(refresh) {
  const btn = $('#btnBriefingRefresh');
  const btnText = btn.textContent;
  btn.disabled = true;
  btn.textContent = '刷新中…';
  if (refresh) toast('正在获取最新数据，如已启用 AI 需等待生成（15~90 秒）…');
  try {
    const b = await api('/api/briefing' + (refresh ? '?refresh=1' : ''));
    renderBriefing(b);
    if (refresh) {
      toast('已刷新' + (b.updatedAt ? ' · ' + b.updatedAt : '') +
        (b.source === 'ai' ? '（AI 简报已重新生成）' : '（聚合实时热榜）'));
    }
  } catch (e) {
    $('#briefingBody').innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = btnText;
  }
}

/* ---------- 提醒 ---------- */
async function loadReminders() {
  let list = [];
  try { list = await api('/api/reminders'); } catch (e) { /* ignore */ }
  const ul = $('#reminderList');
  ul.innerHTML = '';
  if (!list.length) {
    ul.innerHTML = '<li class="empty-li">还没有提醒，添加一条吧 ✏️</li>';
  }
  for (const r of list) {
    const li = document.createElement('li');
    li.className = 'reminder-item' + (r.done ? ' done' : '');
    li.innerHTML = '<label><input type="checkbox"' + (r.done ? ' checked' : '') + '>' +
      '<span class="rt">' + esc(r.text) + '</span></label>' +
      '<button class="del" title="删除">✕</button>';
    li.querySelector('input').onchange = async () => {
      try { await api('/api/reminders/' + r.id + '/toggle', { method: 'POST' }); loadReminders(); }
      catch (e) { toast(e.message, 'err'); }
    };
    li.querySelector('.del').onclick = async () => {
      try { await api('/api/reminders/' + r.id + '/delete', { method: 'POST' }); loadReminders(); }
      catch (e) { toast(e.message, 'err'); }
    };
    ul.appendChild(li);
  }
  const pending = list.filter((r) => !r.done).length;
  $('#reminderBadge').textContent = list.length ? pending + ' 条待办' : '';
  $('#reminderSummary').textContent = list.length ? ('共 ' + list.length + ' 条 · 待办 ' + pending + ' 条') : '';
}

/* ---------- 推送（登录后可见） ---------- */
async function pushTarget(target, force) {
  if (!getToken()) { openModal(); return; }
  try {
    await api('/api/admin/push', { method: 'POST', body: { target: target, force: !!force } });
    toast('已推送到企业微信，去群里看看吧 🔔');
    loadLogs();
  } catch (e) {
    toast(e.message, 'err');
  }
}

/* ---------- 管理弹窗 ---------- */
function openModal() {
  $('#adminModal').classList.remove('hidden');
  if (getToken()) showAdmin(); else showLogin();
}
function closeModal() { $('#adminModal').classList.add('hidden'); }

function showLogin() {
  $('#loginView').classList.remove('hidden');
  $('#adminView').classList.add('hidden');
  $('#passwordInput').value = '';
  setTimeout(() => $('#passwordInput').focus(), 60);
}

async function showAdmin() {
  $('#loginView').classList.add('hidden');
  $('#adminView').classList.remove('hidden');
  try {
    await Promise.all([loadAdminConfig(), loadLogs()]);
  } catch (e) {
    toast(e.message, 'err');
  }
}

async function doLogin() {
  const password = $('#passwordInput').value;
  if (!password) { toast('请输入密码', 'err'); return; }
  try {
    const r = await api('/api/auth/login', { method: 'POST', body: { password: password } });
    setToken(r.token);
    updateAdminUi();
    await showAdmin();
    toast('登录成功 ✅');
  } catch (e) {
    toast(e.message, 'err');
  }
}

/* ---------- 管理配置 ---------- */
const SCHED_FIELDS = {
  poem: { chk: '#cfgSchedPoemEnabled', time: '#cfgSchedPoemTime' },
  briefing: { chk: '#cfgSchedBriefingEnabled', time: '#cfgSchedBriefingTime' },
  reminders: { chk: '#cfgSchedRemindersEnabled', time: '#cfgSchedRemindersTime' },
};

async function loadAdminConfig() {
  const c = await api('/api/admin/config');
  $('#cfgWebhook').value = c.wechat.webhook || '';
  $('#cfgAiEnabled').checked = !!c.ai.enabled;
  $('#cfgAiBaseUrl').value = c.ai.baseUrl || '';
  $('#cfgAiKey').value = c.ai.apiKey || '';
  $('#cfgAiModel').value = c.ai.model || '';
  $('#cfgAiPrompt').value = c.ai.prompt || '';
  for (const key of Object.keys(SCHED_FIELDS)) {
    const s = c.schedules[key] || {};
    $(SCHED_FIELDS[key].chk).checked = !!s.enabled;
    $(SCHED_FIELDS[key].time).value = s.time || '';
  }
}

function collectConfig() {
  const schedules = {};
  for (const key of Object.keys(SCHED_FIELDS)) {
    schedules[key] = {
      enabled: $(SCHED_FIELDS[key].chk).checked,
      time: $(SCHED_FIELDS[key].time).value || '08:00',
    };
  }
  return {
    wechat: { webhook: $('#cfgWebhook').value.trim() },
    ai: {
      enabled: $('#cfgAiEnabled').checked,
      baseUrl: $('#cfgAiBaseUrl').value.trim(),
      apiKey: $('#cfgAiKey').value.trim(),
      model: $('#cfgAiModel').value.trim(),
      prompt: $('#cfgAiPrompt').value,
    },
    schedules: schedules,
  };
}

async function saveConfig(silent) {
  await api('/api/admin/config', { method: 'POST', body: collectConfig() });
  if (!silent) toast('配置已保存 ✅');
}

/* ---------- 推送日志 ---------- */
const TARGET_NAMES = { poem: '每日古诗', briefing: '科技简报', reminders: '每日提醒', test: '推送测试' };

async function loadLogs() {
  let logs = [];
  try { logs = await api('/api/admin/logs'); } catch (e) { return; }
  const ul = $('#logList');
  if (!logs.length) { ul.innerHTML = '<li class="muted">暂无日志</li>'; return; }
  ul.innerHTML = logs.slice(0, 30).map((l) =>
    '<li class="' + (l.ok ? '' : 'fail') + '"><span class="log-time">' + esc(l.time) + '</span>' +
    '<span>' + (l.ok ? '✅' : '❌') + ' ' + esc(TARGET_NAMES[l.target] || l.target) + ' · ' + esc(l.detail || '') + '</span></li>'
  ).join('');
}

/* ---------- 通用：先保存配置，再执行动作 ---------- */
async function withConfig(fn) {
  try {
    await saveConfig(true);
    await fn();
  } catch (e) {
    toast(e.message, 'err');
  }
}

function updateAdminUi() {
  const has = !!getToken();
  $$('.admin-only').forEach((el) => el.classList.toggle('hidden', !has));
  $('#btnSettings').textContent = has ? '⚙ 管理' : '⚙ 设置';
}

/* ---------- 初始化 ---------- */
window.addEventListener('DOMContentLoaded', () => {
  renderDate();
  updateAdminUi();
  loadPoem(false);
  loadBriefing(false);
  loadReminders();

  // 顶栏
  $('#btnSettings').onclick = openModal;
  $('#btnRefreshAll').onclick = async () => {
    const btn = $('#btnRefreshAll');
    if (btn.disabled) return;
    btn.disabled = true;
    btn.classList.add('spinning');
    btn.querySelector('.icon').textContent = '⟳';
    try {
      await Promise.all([loadPoem(false), loadBriefing(false), loadReminders()]);
      const d = new Date();
      toast('已刷新全部栏目 · ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'));
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      btn.disabled = false;
      btn.classList.remove('spinning');
    }
  };

  // 各栏按钮
  $('#btnPoemRefresh').onclick = () => loadPoem(true);
  $('#btnBriefingRefresh').onclick = () => loadBriefing(true);
  $('#btnPoemPush').onclick = () => pushTarget('poem');
  $('#btnBriefingPush').onclick = () => pushTarget('briefing');
  $('#btnRemindersPush').onclick = () => pushTarget('reminders');

  // 提醒添加
  $('#reminderForm').onsubmit = async (ev) => {
    ev.preventDefault();
    const input = $('#reminderInput');
    const text = input.value.trim();
    if (!text) return;
    try {
      await api('/api/reminders', { method: 'POST', body: { text: text } });
      input.value = '';
      loadReminders();
    } catch (e) { toast(e.message, 'err'); }
  };

  // 弹窗
  $('#btnCloseModal').onclick = closeModal;
  document.querySelector('.modal-mask').onclick = closeModal;
  $('#btnLogin').onclick = doLogin;
  $('#passwordInput').onkeydown = (ev) => { if (ev.key === 'Enter') doLogin(); };

  // 企业微信
  $('#btnWechatPreview').onclick = () => withConfig(async () => {
    await api('/api/admin/push', { method: 'POST', body: { target: 'test' } });
    toast('测试消息已推送，请到企业微信群查看 🔔');
    loadLogs();
  });

  // AI 助理
  $('#btnAiTest').onclick = () => withConfig(async () => {
    const r = await api('/api/admin/ai/test', { method: 'POST' });
    toast('AI 连接成功：' + (r.reply || 'OK').slice(0, 30));
  });
  $('#btnAiPreview').onclick = () => withConfig(async () => {
    toast('AI 正在生成简报，约需 15~90 秒，请稍候…');
    const b = await api('/api/admin/ai/preview', { method: 'POST' });
    const box = $('#aiPreviewBox');
    box.classList.remove('hidden');
    box.textContent = b.markdown || (b.items ? b.items.map((i) => i.t ? '【' + i.s + '】' + i.t : i).join('\n') : (b.note || '（空）'));
    renderBriefing(b);
    toast('简报已生成（今日缓存已更新）');
  });
  $('#btnAiPush').onclick = () => withConfig(async () => {
    toast('AI 正在生成简报，生成后推送到企业微信（约需 15~90 秒）…');
    await api('/api/admin/push', { method: 'POST', body: { target: 'briefing', force: true } });
    toast('简报预览已推送到企业微信 🔔');
    loadLogs();
  });

  // 定时推送行内的推送预览
  $$('button[data-push]').forEach((btn) => {
    btn.onclick = () => withConfig(async () => {
      await api('/api/admin/push', { method: 'POST', body: { target: btn.dataset.push } });
      toast('已推送「' + (TARGET_NAMES[btn.dataset.push] || btn.dataset.push) + '」预览到企业微信 🔔');
      loadLogs();
    });
  });

  // 保存 / 密码 / 退出
  $('#btnSaveConfig').onclick = () => withConfig(() => { toast('配置已保存 ✅'); });
  $('#btnChangePassword').onclick = async () => {
    const oldPassword = $('#oldPassword').value, newPassword = $('#newPassword').value;
    try {
      const r = await api('/api/admin/password', { method: 'POST', body: { oldPassword: oldPassword, newPassword: newPassword } });
      setToken(r.token);
      $('#oldPassword').value = ''; $('#newPassword').value = '';
      toast('密码修改成功 ✅');
    } catch (e) { toast(e.message, 'err'); }
  };
  $('#btnLogout').onclick = () => { setToken(''); updateAdminUi(); showLogin(); };
});
