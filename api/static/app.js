const state = {
  currentRun: null,
  currentRunId: null,
  activeTab: "report",
};

const els = {
  runForm: document.querySelector("#runForm"),
  runButton: document.querySelector("#runButton"),
  refreshRunsButton: document.querySelector("#refreshRunsButton"),
  topicInput: document.querySelector("#topicInput"),
  sourceUrlsInput: document.querySelector("#sourceUrlsInput"),
  actorInput: document.querySelector("#actorInput"),
  actorRoleInput: document.querySelector("#actorRoleInput"),
  autoDiscoverInput: document.querySelector("#autoDiscoverInput"),
  liveFetchInput: document.querySelector("#liveFetchInput"),
  fetchLimitInput: document.querySelector("#fetchLimitInput"),
  discoveryLimitInput: document.querySelector("#discoveryLimitInput"),
  runStatePill: document.querySelector("#runStatePill"),
  qualityPill: document.querySelector("#qualityPill"),
  runIdValue: document.querySelector("#runIdValue"),
  statusValue: document.querySelector("#statusValue"),
  sensitivityValue: document.querySelector("#sensitivityValue"),
  modelValue: document.querySelector("#modelValue"),
  synthesisValue: document.querySelector("#synthesisValue"),
  sourcesValue: document.querySelector("#sourcesValue"),
  runsCount: document.querySelector("#runsCount"),
  runsList: document.querySelector("#runsList"),
  messageBar: document.querySelector("#messageBar"),
  reportOutput: document.querySelector("#reportOutput"),
  evidenceTable: document.querySelector("#evidenceTable"),
  claimsTable: document.querySelector("#claimsTable"),
  reviewStatusValue: document.querySelector("#reviewStatusValue"),
  reviewByValue: document.querySelector("#reviewByValue"),
  reviewerInput: document.querySelector("#reviewerInput"),
  reviewNotesInput: document.querySelector("#reviewNotesInput"),
  loadAuditButton: document.querySelector("#loadAuditButton"),
  auditOutput: document.querySelector("#auditOutput"),
};

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  loadRuns();
});

function bindEvents() {
  els.runForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await runResearch();
  });

  els.refreshRunsButton.addEventListener("click", loadRuns);
  els.loadAuditButton.addEventListener("click", loadAuditEvents);

  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tab));
  });

  document.querySelectorAll("[data-review-decision]").forEach((button) => {
    button.addEventListener("click", () => submitReview(button.dataset.reviewDecision));
  });
}

async function runResearch() {
  setBusy(true);
  showMessage("");
  setPill(els.runStatePill, "running", "warn");

  const payload = {
    topic: els.topicInput.value.trim(),
    use_live_fetch: els.liveFetchInput.checked,
    actor_id: els.actorInput.value.trim() || "demo_analyst",
    actor_role: els.actorRoleInput.value,
    auto_discover_sources: els.autoDiscoverInput.checked,
  };
  const sourceUrls = els.sourceUrlsInput.value
    .split(/\n|,/)
    .map((value) => value.trim())
    .filter(Boolean);
  if (sourceUrls.length) {
    payload.source_urls = sourceUrls;
  }
  const fetchLimit = Number(els.fetchLimitInput.value);
  if (Number.isFinite(fetchLimit) && fetchLimit > 0) {
    payload.fetch_limit = fetchLimit;
  }
  const discoveryLimit = Number(els.discoveryLimitInput.value);
  if (Number.isFinite(discoveryLimit) && discoveryLimit > 0) {
    payload.discovery_max_sources = discoveryLimit;
  }

  try {
    const run = await api("/research/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.currentRun = run;
    state.currentRunId = run.run_id;
    renderRunSummary(run);
    await loadRunArtifacts(run);
    await loadRuns();
    activateTab("report");
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(false);
  }
}

async function loadRuns() {
  try {
    const payload = await api("/research/runs");
    const runs = payload.runs || [];
    els.runsCount.textContent = String(runs.length);
    els.runsList.innerHTML = "";

    if (!runs.length) {
      els.runsList.innerHTML = '<p class="muted">No runs yet.</p>';
      return;
    }

    runs.slice(0, 20).forEach((run) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `run-item ${run.run_id === state.currentRunId ? "active" : ""}`;
      button.innerHTML = `
        <strong>${escapeHtml(run.topic || "Research run")}</strong>
        <span>${escapeHtml(run.run_id)} / ${escapeHtml(run.status)} / ${escapeHtml(run.quality_gate)}</span>
      `;
      button.addEventListener("click", () => selectRun(run.run_id));
      els.runsList.appendChild(button);
    });
  } catch (error) {
    showMessage(error.message);
  }
}

async function selectRun(runId) {
  showMessage("");
  try {
    const run = await api(`/research/runs/${encodeURIComponent(runId)}/status`);
    state.currentRun = run;
    state.currentRunId = run.run_id;
    renderRunSummary(run);
    await loadRunArtifacts(run);
    await loadRuns();
  } catch (error) {
    showMessage(error.message);
  }
}

async function loadRunArtifacts(run) {
  if (run.links.report) {
    const report = await api(run.links.report);
    els.reportOutput.textContent = report.markdown || "";
  } else {
    els.reportOutput.textContent = "No report artifact for this run.";
  }

  if (run.links.evidence) {
    const evidence = await api(run.links.evidence);
    renderEvidence(evidence.items || []);
  } else {
    renderEvidence([]);
  }

  if (run.links.claims) {
    const claims = await api(run.links.claims);
    renderClaims(claims.items || []);
  } else {
    renderClaims([]);
  }

  renderReview(run.review || {});
  renderAuditSnapshot(run);
}

async function submitReview(decision) {
  if (!state.currentRunId) {
    showMessage("Select a run first.");
    return;
  }

  try {
    const payload = await api(`/research/runs/${encodeURIComponent(state.currentRunId)}/review`, {
      method: "POST",
      body: JSON.stringify({
        actor_id: els.reviewerInput.value.trim() || "demo_reviewer",
        actor_role: "reviewer",
        decision,
        notes: els.reviewNotesInput.value.trim() || null,
      }),
    });
    renderReview(payload.review || {});
    await selectRun(state.currentRunId);
    activateTab("review");
  } catch (error) {
    showMessage(error.message);
  }
}

async function loadAuditEvents() {
  try {
    const actorId = "demo_admin";
    const payload = await api(`/admin/audit-events?actor_id=${actorId}&actor_role=admin&limit=30`);
    els.auditOutput.textContent = JSON.stringify(payload.items || [], null, 2);
  } catch (error) {
    showMessage(error.message);
  }
}

function renderRunSummary(run) {
  const model = run.model_gateway || {};
  const sourcePolicy = run.source_policy || {};

  els.runIdValue.textContent = run.run_id || "-";
  els.statusValue.textContent = run.status || "-";
  els.sensitivityValue.textContent = run.sensitivity || "-";
  els.modelValue.textContent = [model.provider, model.model].filter(Boolean).join(" / ") || "-";
  els.synthesisValue.textContent = model.synthesis_status || "-";
  els.sourcesValue.textContent = String(sourcePolicy.allowed_source_count ?? "-");

  setPill(els.runStatePill, run.status || "idle", run.status || "neutral");
  setPill(els.qualityPill, run.quality_gate || "not started", run.quality_gate || "neutral");
  renderReview(run.review || {});
}

function renderEvidence(items) {
  els.evidenceTable.innerHTML = "";
  items.forEach((item) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(item.source_id || "-")}</td>
      <td>${escapeHtml(item.source_type || "-")}</td>
      <td>${escapeHtml(item.research_block || "-")}</td>
      <td>${formatScore(item.relevance_score)}</td>
      <td>${escapeHtml(trimText(item.text || "", 360))}</td>
    `;
    els.evidenceTable.appendChild(row);
  });
  if (!items.length) {
    els.evidenceTable.innerHTML = '<tr><td colspan="5">No evidence loaded.</td></tr>';
  }
}

function renderClaims(items) {
  els.claimsTable.innerHTML = "";
  items.forEach((item) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(item.claim_id || "-")}</td>
      <td>${escapeHtml(item.confidence || "-")}</td>
      <td>${escapeHtml((item.evidence_ids || []).join(", "))}</td>
      <td>${escapeHtml(trimText(item.claim_text || "", 360))}</td>
    `;
    els.claimsTable.appendChild(row);
  });
  if (!items.length) {
    els.claimsTable.innerHTML = '<tr><td colspan="4">No claims loaded.</td></tr>';
  }
}

function renderReview(review) {
  els.reviewStatusValue.textContent = review.status || "-";
  els.reviewByValue.textContent = review.updated_by || "-";
}

function renderAuditSnapshot(run) {
  const payload = {
    run_id: run.run_id,
    audit: run.audit,
    review: run.review,
    source_policy: run.source_policy,
    model_gateway: run.model_gateway,
  };
  els.auditOutput.textContent = JSON.stringify(payload, null, 2);
}

function activateTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `${tabName}Tab`);
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.detail || `Request failed: ${response.status}`);
  }
  return data;
}

function setBusy(isBusy) {
  els.runButton.disabled = isBusy;
  els.runButton.textContent = isBusy ? "Running..." : "Run pipeline";
}

function setPill(element, text, status) {
  element.textContent = text;
  element.className = `pill ${status}`;
}

function showMessage(message) {
  if (!message) {
    els.messageBar.hidden = true;
    els.messageBar.textContent = "";
    return;
  }
  els.messageBar.hidden = false;
  els.messageBar.textContent = message;
}

function formatScore(value) {
  if (typeof value !== "number") {
    return "-";
  }
  return value.toFixed(3);
}

function trimText(value, maxLength) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 3)}...`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
