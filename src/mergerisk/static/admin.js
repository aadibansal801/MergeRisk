const csrf = document.querySelector('meta[name="csrf-token"]').content;
const main = document.querySelector('#main');
const isSuper = main.dataset.role === 'super_admin';
const myId = main.dataset.id;
const $ = (selector) => document.querySelector(selector);
const SVG = 'http://www.w3.org/2000/svg';
let allUsers = [];
let activeUser = '';

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

// A cell is a plain value, {text, num}, or a DOM node to wrap.
function row(body, cells) {
  const tr = document.createElement('tr');
  for (const cell of cells) {
    const td = el('td');
    if (cell instanceof Node) {
      td.append(cell);
    } else if (cell !== null && typeof cell === 'object') {
      td.textContent = String(cell.text);
      if (cell.num) td.className = 'num';
    } else {
      td.textContent = String(cell);
    }
    tr.append(td);
  }
  body.append(tr);
}

function empty(body, columns, text) {
  const tr = document.createElement('tr');
  const td = el('td', text, 'muted');
  td.colSpan = columns;
  tr.append(td);
  body.replaceChildren(tr);
}

const when = (seconds) => (seconds ? new Date(seconds * 1000).toLocaleString() : 'Never');
const day = (seconds) => (seconds ? new Date(seconds * 1000).toLocaleDateString() : '');

async function api(path, options = {}) {
  const init = { method: options.method || 'GET', headers: {} };
  if (init.method !== 'GET') init.headers['X-CSRF-Token'] = csrf;
  if (options.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  if (response.status === 401) {
    location.assign('/admin/login');
    throw new Error('Signed out');
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(typeof detail.detail === 'string' ? detail.detail : 'Request failed.');
  }
  return response.status === 204 ? null : response.json();
}

function say(node, text, bad) {
  node.textContent = text;
  node.classList.toggle('ok', !bad);
  node.hidden = !text;
}

function tiles(totals, days) {
  const items = [
    ['Registered users', totals.users, 'all time'],
    ['Active users', totals.active_users, `last ${days} days`],
    ['New users', totals.new_users, `last ${days} days`],
    ['Sign-ins', totals.period_logins, `${totals.logins} all time`],
    ['Analyses run', totals.period_analyses, `${totals.analyses} all time`],
  ];
  $('#tiles').replaceChildren(...items.map(([label, value, note]) => {
    const tile = el('div', undefined, 'tile');
    tile.append(el('span', label, 'tile-label'), el('strong', value.toLocaleString(), 'tile-value'),
      el('span', note, 'muted'));
    return tile;
  }));
}

function chart(series) {
  const width = 720, height = 220, left = 34, bottom = 24, top = 8;
  const peak = Math.max(1, ...series.map((point) => Math.max(point.logins, point.analyses)));
  const step = (width - left) / series.length;
  const bar = Math.max(2, Math.min(14, step / 2.6));
  const plot = height - top - bottom;
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('class', 'chart-svg');
  const add = (parent, tag, attrs, text) => {
    const node = document.createElementNS(SVG, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    parent.append(node);
    return node;
  };
  for (const fraction of [0, 0.5, 1]) {
    const y = top + plot * (1 - fraction);
    add(svg, 'line', { x1: left, x2: width, y1: y, y2: y, class: 'grid' });
    add(svg, 'text', { x: left - 6, y: y + 4, class: 'axis', 'text-anchor': 'end' }, Math.round(peak * fraction));
  }
  series.forEach((point, index) => {
    const x = left + index * step + step / 2;
    for (const [key, offset, cls] of [['logins', -bar, 'bar-logins'], ['analyses', 0, 'bar-analyses']]) {
      const h = (point[key] / peak) * plot;
      const rect = add(svg, 'rect', { x: x + offset, y: top + plot - h, width: bar, height: h, class: cls });
      add(rect, 'title', {}, `${point.date}: ${point.analyses} analyses, ${point.logins} sign-ins, ${point.users} users`);
    }
    if (index % Math.ceil(series.length / 8) === 0) {
      add(svg, 'text', { x, y: height - 6, class: 'axis', 'text-anchor': 'middle' }, point.date.slice(5));
    }
  });
  $('#chart').replaceChildren(svg);
}

function renderUsers() {
  const needle = $('#filter').value.trim().toLowerCase();
  const body = $('#users');
  body.replaceChildren();
  const users = allUsers.filter((user) => user.login.toLowerCase().includes(needle));
  if (!users.length) return empty(body, 5, 'No users match.');
  for (const user of users) {
    const link = el('button', user.login, 'text-button');
    link.type = 'button';
    link.title = 'Show this user’s activity';
    link.addEventListener('click', () => { activeUser = user.github_id; loadFeed(user.login).catch(showError); });
    row(body, [link, { text: user.logins, num: true }, { text: user.analyses, num: true },
      when(user.last_active), day(user.joined)]);
  }
}

async function loadFeed(label) {
  const events = await api('/admin/api/activity?limit=100' + (activeUser ? `&github_id=${encodeURIComponent(activeUser)}` : ''));
  const body = $('#feed');
  body.replaceChildren();
  $('#feed-scope').textContent = activeUser ? `for ${label}` : '';
  if (!events.length) return empty(body, 3, 'No activity yet.');
  for (const event of events) {
    row(body, [when(event.created), event.login,
      event.kind === 'analysis' ? `Analysis of ${event.repository || 'a repository'}` : 'Signed in']);
  }
}

const showError = (error) => say($('#load-error'), error.message, true);

async function load() {
  say($('#load-error'), '');
  try {
    const stats = await api(`/admin/api/stats?days=${$('#range').value}`);
    tiles(stats.totals, stats.days);
    chart(stats.series);
    allUsers = stats.users;
    renderUsers();
    const repos = $('#repos');
    repos.replaceChildren();
    if (!stats.repositories.length) empty(repos, 3, 'No analyses in this period.');
    for (const repo of stats.repositories) {
      row(repos, [repo.repository, { text: repo.runs, num: true }, { text: repo.users, num: true }]);
    }
    activeUser = '';
    await loadFeed('');
    if (isSuper) await loadAdmins();
  } catch (error) {
    showError(error);
  }
}

async function loadAdmins() {
  $('#admins-panel').hidden = false;
  const admins = await api('/admin/api/admins');
  const body = $('#admins');
  body.replaceChildren();
  for (const admin of admins) {
    const actions = el('div', undefined, 'actions');
    if (admin.role === 'admin') {
      const reset = el('button', 'Reset password', 'text-button');
      reset.type = 'button';
      reset.addEventListener('click', async () => {
        const next = prompt(`New password for ${admin.email}`);
        if (!next) return;
        try {
          await api(`/admin/api/admins/${admin.id}/password`, { method: 'POST', body: { password: next } });
          say($('#admin-message'), 'Password updated.');
        } catch (error) { say($('#admin-message'), error.message, true); }
      });
      const remove = el('button', 'Remove', 'text-button danger');
      remove.type = 'button';
      remove.addEventListener('click', async () => {
        if (!confirm(`Remove ${admin.email}? They will be signed out immediately.`)) return;
        try {
          await api(`/admin/api/admins/${admin.id}`, { method: 'DELETE' });
          await loadAdmins();
        } catch (error) { say($('#admin-message'), error.message, true); }
      });
      actions.append(reset, remove);
    }
    row(body, [admin.email + (admin.id === myId ? ' (you)' : ''), admin.role === 'super_admin' ? 'Super admin' : 'Admin',
      admin.created_by || '—', day(admin.created), actions]);
  }
}

$('#range').addEventListener('change', load);
$('#filter').addEventListener('input', renderUsers);
$('#logout').addEventListener('click', async () => {
  try { await api('/admin/api/logout', { method: 'POST' }); } finally { location.assign('/admin/login'); }
});
$('#add-admin').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await api('/admin/api/admins', { method: 'POST', body: { email: $('#new-email').value, password: $('#new-password').value } });
    form.reset();
    say($('#admin-message'), 'Admin added.');
    await loadAdmins();
  } catch (error) { say($('#admin-message'), error.message, true); }
});
$('#change-password').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await api('/admin/api/password', { method: 'POST', body: { current: $('#current-password').value, password: $('#next-password').value } });
    form.reset();
    say($('#pw-message'), 'Password updated.');
  } catch (error) { say($('#pw-message'), error.message, true); }
});

load();
