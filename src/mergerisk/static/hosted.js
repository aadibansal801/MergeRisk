const csrf = document.querySelector('meta[name="csrf-token"]').content;
const form = document.querySelector('#analyze');
const statusLine = document.querySelector('#status');
const runs = document.querySelector('#runs');
const report = document.querySelector('#report');
const reportStatus = document.querySelector('#report-status');
const revisions = document.querySelector('#revisions');
const coverage = document.querySelector('#coverage');
const findings = document.querySelector('#findings');
const patch = document.querySelector('#patch');
const patchLink = document.querySelector('#patch-link');
const deleteRun = document.querySelector('#delete-run');
let selected = null;
let refreshTimer;

async function api(path, method = 'GET', input) {
  const response = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: input === undefined ? undefined : JSON.stringify(input),
  });
  if (response.status === 204) return;
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : 'The service is temporarily unavailable.');
  return result;
}

function jobPath(id) { return `/api/jobs/${encodeURIComponent(id)}`; }

function setStatus(message, error = false) {
  statusLine.textContent = message;
  statusLine.classList.toggle('notice', error);
}

function drawJob(job) {
  report.hidden = false;
  const result = job.result || {};
  const states = { queued: 'Waiting for a worker', running: 'Analyzing', complete: 'Analysis complete', error: 'Analysis failed' };
  const outcomes = {
    findings_present: 'Merge-introduced findings detected.',
    no_supported_findings: 'No findings in the supported analysis.',
    partial: 'Analysis was partial. Some Python behavior could not be resolved.',
    failed: 'Analysis could not complete.',
  };
  reportStatus.textContent = job.error || result.message || outcomes[result.status] || states[job.state] || 'Analysis unavailable';
  deleteRun.hidden = !['complete', 'error'].includes(job.state);
  revisions.replaceChildren();
  for (const [label, sha] of [['Merge base', result.base_commit], ['Target', result.target_commit], ['Source', result.source_commit], ['Merge tree', result.merge_tree]]) {
    if (!sha) continue;
    const name = document.createElement('dt');
    const value = document.createElement('dd');
    name.textContent = label;
    value.textContent = sha;
    revisions.append(name, value);
  }
  revisions.hidden = !revisions.childNodes.length;
  coverage.hidden = !result.coverage;
  if (result.coverage) {
    const {files_analyzed = 0, files_skipped = 0, files_unsupported = 0, unresolved_references = 0} = result.coverage;
    coverage.textContent = `${files_analyzed} files analyzed · ${files_skipped} skipped · ${files_unsupported} unsupported · ${unresolved_references} unresolved references`;
  }
  findings.replaceChildren();
  for (const item of result.findings || []) {
    const entry = document.createElement('li');
    const summary = document.createElement('strong');
    summary.textContent = item.summary || item.rule_id || 'Finding';
    const detail = document.createElement('p');
    const location = (item.locations || []).find(place => place.path);
    const source = location && `${location.path}:${location.start_line}`;
    detail.textContent = [source, item.severity, item.rule_id].filter(Boolean).join(' · ');
    entry.append(summary, detail);
    findings.append(entry);
  }
  if (result.finding_count > (result.findings || []).length) {
    const entry = document.createElement('li');
    entry.textContent = `Showing ${result.findings.length} of ${result.finding_count} findings.`;
    findings.append(entry);
  }
  for (const file of result.conflict_files || []) {
    const entry = document.createElement('li');
    entry.textContent = `Conflict in ${file}`;
    findings.append(entry);
  }
  patch.hidden = !job.has_patch;
  if (job.has_patch) patchLink.href = `${jobPath(job.id)}/patch`;
}

async function refresh() {
  clearTimeout(refreshTimer);
  try {
    const jobs = await api('/api/jobs');
    const states = { queued: 'Queued', running: 'Analyzing', complete: 'Complete', error: 'Failed' };
    runs.replaceChildren();
    for (const job of jobs) {
      const item = document.createElement('li');
      const button = document.createElement('button');
      const detail = document.createElement('span');
      button.type = 'button';
      button.className = 'run-link';
      button.textContent = job.request.repository;
      button.addEventListener('click', () => { selected = job.id; refresh(); });
      detail.className = 'run-stats';
      detail.textContent = `${job.request.source} into ${job.request.target} · ${states[job.state] || job.state}`;
      item.append(button, detail);
      runs.append(item);
    }
    setStatus(jobs.length ? '' : 'Your analyses will appear here.');
    const opened = selected;
    if (opened && jobs.some(job => job.id === opened)) {
      const job = await api(jobPath(opened));
      if (selected === opened) drawJob(job);
    }
    if (jobs.some(job => ['queued', 'running'].includes(job.state))) refreshTimer = setTimeout(refresh, 2500);
  } catch (error) {
    setStatus(error.message, true);
    refreshTimer = setTimeout(refresh, 5000);
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    const job = await api('/api/jobs', 'POST', Object.fromEntries(new FormData(form)));
    selected = job.id;
    await refresh();
  } catch (error) {
    clearTimeout(refreshTimer);
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
});

deleteRun.addEventListener('click', async () => {
  try {
    await api(jobPath(selected), 'DELETE');
    selected = null;
    report.hidden = true;
    await refresh();
  } catch (error) { setStatus(error.message, true); }
});

document.querySelector('#logout').addEventListener('click', async () => {
  try { await api('/auth/logout', 'POST'); location.assign('/'); }
  catch (error) { setStatus(error.message, true); }
});

refresh();
