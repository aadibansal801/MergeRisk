const csrf = document.querySelector('meta[name="csrf-token"]').content;
const form = document.querySelector('#analyze');
const runButton = form.querySelector('[type="submit"]');
const formMessage = document.querySelector('#form-message');
const statusLine = document.querySelector('#status');
const runs = document.querySelector('#runs');
const emptyReport = document.querySelector('#empty-report');
const report = document.querySelector('#report');
const reportTitle = document.querySelector('#report-title');
const reportBadge = document.querySelector('#report-badge');
const reportStatus = document.querySelector('#report-status');
const reportActions = document.querySelector('#report-actions');
const revisions = document.querySelector('#revisions');
const revisionDetails = document.querySelector('#revision-details');
const coverage = document.querySelector('#coverage');
const findingsArea = document.querySelector('#findings-area');
const findings = document.querySelector('#findings');
const findingsLimit = document.querySelector('#findings-limit');
const patch = document.querySelector('#patch');
const patchLink = document.querySelector('#patch-link');
const deleteRun = document.querySelector('#delete-run');

const states = {
  queued: ['Queued', 'progress', 'Your comparison is waiting to start.'],
  running: ['Analyzing', 'progress', 'MergeRisk is checking the candidate for Python issues.'],
  complete: ['Complete', 'neutral', ''],
  error: ['Failed', 'error', 'Analysis could not complete.'],
};
const outcomes = {
  no_supported_findings: ['No supported findings', 'Complete', 'success', 'The supported checks found no merge-introduced issues.'],
  textual_conflict: ['Git reported merge conflicts', 'Merge conflict', 'attention', 'Resolve the listed conflicts before analyzing a merged candidate.'],
  inconclusive: ['Comparison inconclusive', 'Inconclusive', 'attention', 'The available inputs could not produce a conclusive report.'],
  already_contained: ['Source already in target', 'Already contained', 'neutral', 'The source commit is already contained in the target branch.'],
  fast_forward: ['Fast-forward merge', 'Fast-forward', 'neutral', 'The target is an ancestor of the source.'],
  failed: ['Analysis could not complete', 'Failed', 'error', ''],
};
const severityTones = { critical: 'error', high: 'error', medium: 'attention' };

let selected = null;
let rendered = null;
let refreshTimer;
let revision = 0;
let historyKey = '';

async function api(path, method = 'GET', input) {
  const response = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: input === undefined ? undefined : JSON.stringify(input),
  });
  if (response.status === 204) return;
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(typeof result.detail === 'string' ? result.detail : 'The service is temporarily unavailable.');
    error.status = response.status;
    throw error;
  }
  return result;
}

function jobPath(id) {
  return `/api/jobs/${encodeURIComponent(id)}`;
}

function element(tag, className, label) {
  const node = document.createElement(tag);
  node.className = className;
  if (label) node.textContent = label;
  return node;
}

function showMessage(node, message) {
  if (node.textContent !== message) node.textContent = message;
  node.hidden = !message;
}

function setStatus(message, error = false) {
  statusLine.classList.toggle('notice', error);
  showMessage(statusLine, message);
}

function showEmptyReport() {
  rendered = null;
  report.hidden = true;
  emptyReport.hidden = false;
}

function drawFindings(result) {
  const entries = result.findings || [];
  const conflicts = result.conflict_files || [];
  const truncated = result.finding_count > entries.length;
  findingsArea.hidden = !(entries.length || conflicts.length || truncated);
  document.querySelector('#findings-title').textContent = conflicts.length ? 'Conflicting files' : 'Findings';
  document.querySelector('#finding-branches').hidden = !entries.some(item => /\b(?:left|right)\b/i.test(item.summary || ''));
  findings.replaceChildren();
  for (const item of entries) {
    const entry = element('li', '');
    const heading = element('div', 'finding-heading');
    heading.append(element('h4', '', item.title || item.rule_id || 'Finding'));
    if (item.severity) {
      const severity = element('span', 'severity', item.severity);
      severity.dataset.tone = severityTones[item.severity] || 'neutral';
      heading.append(severity);
    }
    entry.append(heading);
    if (item.summary && item.summary !== item.title) entry.append(element('p', 'finding-summary', item.summary));
    const details = element('p', 'finding-meta');
    for (const {path, start_line: line} of item.locations || []) {
      if (path) details.append(element('code', '', line ? `${path}:${line}` : path));
    }
    if (item.rule_id) details.append(element('code', '', item.rule_id));
    if (details.childNodes.length) entry.append(details);
    findings.append(entry);
  }
  for (const path of conflicts) {
    const entry = element('li', '');
    entry.append(element('code', '', path));
    findings.append(entry);
  }
  showMessage(findingsLimit, truncated ? `Showing ${entries.length} of ${result.finding_count} findings.` : '');
}

function drawJob(job) {
  const result = job.result || {};
  const [state, tone, description] = states[job.state];
  const count = result.finding_count ?? result.findings?.length ?? 0;
  const countLabel = `${count} merge ${count === 1 ? 'finding' : 'findings'}`;
  let [title, badge, badgeTone, message] = outcomes[result.status] || [state, state, tone, description];
  if (result.status === 'findings_present') {
    [title, badge, badgeTone, message] = [countLabel, 'Review findings', 'attention', 'The issues below were introduced by the merge.'];
  } else if (result.status === 'partial') {
    title = count ? countLabel : 'No findings in covered code';
    [badge, badgeTone, message] = ['Partial coverage', 'attention', 'Some Python behavior could not be resolved. Review coverage before relying on this result.'];
  }
  document.querySelector('#report-repo').textContent = job.request.repository;
  reportTitle.textContent = title;
  showMessage(reportBadge, badge === title ? '' : badge);
  reportBadge.dataset.tone = badgeTone;
  document.querySelector('#report-branches').replaceChildren(
    element('code', '', job.request.source), ' into ', element('code', '', job.request.target),
  );
  showMessage(reportStatus, job.error || (result.status === 'textual_conflict' ? message : result.message || message));
  showMessage(reportActions, '');

  drawFindings(result);
  coverage.hidden = !result.coverage;
  if (result.coverage) {
    const { files_analyzed = 0, files_skipped = 0, files_unsupported = 0, unresolved_references = 0 } = result.coverage;
    document.querySelector('#coverage-summary').textContent = `${files_analyzed} ${files_analyzed === 1 ? 'file' : 'files'} analyzed · ${files_skipped} skipped · ${files_unsupported} unsupported · ${unresolved_references} unresolved ${unresolved_references === 1 ? 'reference' : 'references'}`;
  }

  revisions.replaceChildren();
  for (const [label, sha] of [['Merge base', result.base_commit], ['Target', result.target_commit], ['Source', result.source_commit], ['Merge tree', result.merge_tree]]) {
    if (sha) revisions.append(element('dt', '', label), element('dd', '', sha));
  }
  revisionDetails.hidden = !revisions.childNodes.length;
  if (rendered?.id !== job.id) revisionDetails.open = false;
  patch.hidden = !job.has_patch;
  if (job.has_patch) patchLink.href = `${jobPath(job.id)}/patch`;
  else patchLink.removeAttribute('href');
  deleteRun.hidden = job.state !== 'complete' && job.state !== 'error';
  emptyReport.hidden = true;
  report.hidden = false;
  rendered = job;
}

function drawHistory(jobs) {
  const key = JSON.stringify(jobs.map(({ id, state }) => [id, state]));
  if (key !== historyKey) {
    const focusedId = document.activeElement.dataset.runId;
    runs.replaceChildren();
    for (const job of jobs) {
      const item = element('li', '');
      const button = element('button', 'run-link');
      button.type = 'button';
      button.dataset.runId = job.id;
      const [label, tone] = states[job.state];
      const badge = element('span', 'run-badge', label);
      badge.dataset.tone = tone;
      button.append(element('span', 'run-repo', job.request.repository), badge,
        element('span', 'run-stats', `${job.request.source} into ${job.request.target}`));
      button.addEventListener('click', () => openRun(job.id).catch(error => setStatus(error.message, true)));
      item.append(button);
      runs.append(item);
    }
    if (focusedId) {
      const replacement = Array.from(runs.querySelectorAll('button')).find(button => button.dataset.runId === focusedId);
      replacement?.focus({ preventScroll: true });
    }
    historyKey = key;
  }
  for (const button of runs.querySelectorAll('button')) {
    button.setAttribute('aria-pressed', String(button.dataset.runId === selected));
  }
}

async function refresh() {
  const request = ++revision;
  clearTimeout(refreshTimer);
  try {
    const jobs = await api('/api/jobs');
    if (request !== revision) return;
    const opened = jobs.find(job => job.id === selected);
    if (selected && !opened) {
      selected = null;
      showEmptyReport();
    }
    drawHistory(jobs);
    setStatus(jobs.length ? '' : 'Your analyses will appear here.');
    if (opened && (opened.id !== rendered?.id || opened.state !== rendered.state || opened.updated !== rendered.updated)) {
      const detail = await api(jobPath(opened.id));
      if (request !== revision) return;
      drawJob(detail);
    }
    if (jobs.some(job => job.state === 'queued' || job.state === 'running')) refreshTimer = setTimeout(refresh, 2000);
  } catch (error) {
    if (request !== revision) return;
    setStatus(error.message, true);
    if (error.status !== 401) refreshTimer = setTimeout(refresh, 5000);
  }
}

async function openRun(id) {
  selected = id;
  await refresh();
  if (rendered?.id === id && selected === id) reportTitle.focus();
}

document.querySelector('#use-sample').addEventListener('click', () => {
  form.elements.repository.value = 'https://github.com/aadibansal801/mergerisk-fulfillment-fixture';
  form.elements.target.value = 'shipping/trim-imports';
  form.elements.source.value = 'shipping/carrier-export';
  showMessage(formMessage, '');
});

form.addEventListener('input', () => showMessage(formMessage, ''));
form.addEventListener('submit', async event => {
  event.preventDefault();
  const input = Object.fromEntries(new FormData(form));
  showMessage(formMessage, '');
  if (input.target.trim() === input.source.trim()) {
    showMessage(formMessage, 'Choose two different branches.');
    form.elements.source.focus();
    return;
  }
  runButton.disabled = true;
  runButton.textContent = 'Submitting…';
  try {
    const job = await api('/api/jobs', 'POST', input);
    await openRun(job.id);
  } catch (error) {
    showMessage(formMessage, error.message);
  } finally {
    runButton.disabled = false;
    runButton.textContent = 'Run analysis';
  }
});

deleteRun.addEventListener('click', async () => {
  const id = rendered.id;
  deleteRun.disabled = true;
  try {
    await api(jobPath(id), 'DELETE');
    if (selected === id) {
      selected = null;
      showEmptyReport();
      runButton.focus();
    }
    await refresh();
  } catch (error) {
    if (rendered?.id === id) showMessage(reportActions, error.message);
  } finally {
    deleteRun.disabled = false;
  }
});

document.querySelector('#logout').addEventListener('click', async () => {
  try {
    await api('/auth/logout', 'POST');
    location.assign('/');
  } catch (error) {
    showMessage(formMessage, error.message);
  }
});

refresh();
