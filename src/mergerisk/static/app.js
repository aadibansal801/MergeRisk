"use strict";
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const feedback = document.getElementById("feedback");
function error(message) {
  feedback.textContent = message;
  feedback.hidden = false;
  feedback.focus();
}
async function api(url, data) {
  const response = await fetch(url, data === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
    body: JSON.stringify(data)
  });
  // Proxies, crashes and 5xx pages are not JSON; report the HTTP status instead of a parse error.
  const result = await response.json().catch(() => ({detail: "Request failed (HTTP " + response.status + ")"}));
  if (!response.ok) {
    const detail = typeof result.detail === "string" ? result.detail : JSON.stringify(result.detail || result);
    throw new Error(detail);
  }
  return result;
}
function expected() {
  const context = document.getElementById("run-context");
  return {expected: context.dataset.expected, version: Number(context.dataset.version)};
}
for (const form of document.querySelectorAll("form[data-action]")) {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    feedback.hidden = true;
    const button = form.querySelector('button[type="submit"]');
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Working…";
    const data = Object.fromEntries(new FormData(form));
    const action = form.dataset.action;
    try {
      let url, payload;
      if (action === "repository") { url = "/api/repositories"; payload = data; }
      else if (action === "analyze") { url = "/api/runs"; payload = data; }
      else if (action === "settings") {
        url = "/api/repositories/" + form.dataset.repo + "/settings";
        payload = {image: data.image.trim(), command: data.command.trim() ? JSON.parse(data.command) : [], timeout: Number(data.timeout)};
      } else if (action === "cancel") { url = "/api/runs/" + form.dataset.run + "/cancel"; payload = {}; }
      else {
        const context = document.getElementById("run-context");
        url = "/api/runs/" + context.dataset.id + "/" + action;
        payload = expected();
        if (action === "commit") payload.allow_partial = Boolean(data.allow_partial);
        if (action === "apply") payload.confirm = Boolean(data.confirm);
        if (action === "review") {
          payload.accepted = []; payload.rejected = [];
          for (const [key, value] of Object.entries(data)) {
            if (key.startsWith("suggestion-")) payload[value].push(key.slice(11));
          }
        }
      }
      const response = await api(url, payload);
      if (response.redirect) window.location.assign(response.redirect);
      else if (action === "settings") {
        button.textContent = "Settings saved";
        button.disabled = false;
      } else window.location.reload();
    } catch (e) {
      error(e.message); button.disabled = false; button.textContent = original;
    }
  });
}
const selector = document.querySelector("[data-repository-selector]");
async function branches() {
  const button = document.getElementById("analyze-button");
  const left = document.getElementById("left"), right = document.getElementById("right");
  const health = document.getElementById("repo-health");
  button.disabled = true; left.disabled = true; right.disabled = true;
  health.textContent = "Loading branches…";
  try {
    const result = await api("/api/repositories/" + selector.value + "/branches");
    for (const select of [left, right]) {
      select.replaceChildren();
      for (const branch of result.branches) {
        const option = document.createElement("option");
        option.value = branch.name; option.textContent = branch.name + " · " + branch.sha.slice(0, 8);
        select.append(option);
      }
      select.disabled = !result.branches.length;
    }
    const headBranch = result.branches.find(b => b.sha === result.head);
    if (headBranch) left.value = headBranch.name;
    const source = result.branches.find(b => b.name !== left.value);
    if (source) right.value = source.name;
    health.textContent = result.health + " · HEAD " + result.head.slice(0, 12) +
      (result.branches.length < 2 ? " · Create another branch to compare." : "");
    button.disabled = result.branches.length < 2;
  } catch (e) { health.textContent = "Unable to load branches."; error(e.message); }
}
if (selector) { selector.addEventListener("change", branches); branches(); }
const polling = document.querySelector("[data-poll]");
if (polling) {
  let pollingDelay = 1000;
  async function poll() {
    try {
      const run = await api("/api/runs/" + polling.dataset.poll);
      if (!["queued", "running", "cancelling", "validating"].includes(run.state)) {
        window.location.reload(); return;
      }
      document.getElementById("job-state").textContent = run.state;
      document.getElementById("job-progress").textContent = run.progress;
      pollingDelay = 1000;
    } catch (e) {
      document.getElementById("job-progress").textContent = "Connection interrupted. Retrying…";
      pollingDelay = Math.min(pollingDelay * 2, 10000);
    }
    window.setTimeout(poll, pollingDelay);
  }
  window.setTimeout(poll, pollingDelay);
}
for (const select of document.querySelectorAll("[data-compare]")) {
  select.addEventListener("change", () => {
    for (const pre of document.getElementById(select.dataset.compare).querySelectorAll("[data-version]"))
      pre.hidden = pre.dataset.version !== select.value;
  });
}
const search = document.querySelector("[data-finding-search]");
const severity = document.querySelector("[data-severity]:is(select)");
function filterFindings() {
  let visible = 0;
  for (const finding of document.querySelectorAll("[data-finding]")) {
    const show = finding.textContent.toLowerCase().includes(search.value.toLowerCase()) &&
      (!severity.value || finding.dataset.severity === severity.value);
    finding.hidden = !show;
    if (show) visible++;
  }
  document.getElementById("no-finding-matches").hidden = visible > 0;
}
if (search) { search.addEventListener("input", filterFindings); severity.addEventListener("change", filterFindings); }
