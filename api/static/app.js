const state = {
  currentRun: null,
  currentRunId: null,
  activeTab: "report",
  selectedFiles: [],
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
  attachButton: document.querySelector("#attachButton"),
  attachMenu: document.querySelector("#attachMenu"),
  uploadDocsButton: document.querySelector("#uploadDocsButton"),
  clearFilesButton: document.querySelector("#clearFilesButton"),
  fileInput: document.querySelector("#fileInput"),
  selectedFiles: document.querySelector("#selectedFiles"),
  promptDropZone: document.querySelector("#promptDropZone"),
  qualityPill: document.querySelector("#qualityPill"),
  runIdValue: document.querySelector("#runIdValue"),
  statusValue: document.querySelector("#statusValue"),
  modelValue: document.querySelector("#modelValue"),
  sourcesValue: document.querySelector("#sourcesValue"),
  runsCount: document.querySelector("#runsCount"),
  runsList: document.querySelector("#runsList"),
  messageBar: document.querySelector("#messageBar"),
  reportOutput: document.querySelector("#reportOutput"),
  evidenceTable: document.querySelector("#evidenceTable"),
  claimsTable: document.querySelector("#claimsTable"),
  graphSummary: document.querySelector("#graphSummary"),
  graphList: document.querySelector("#graphList"),
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
  els.attachButton.addEventListener("click", toggleAttachMenu);
  els.uploadDocsButton.addEventListener("click", () => {
    els.attachMenu.hidden = true;
    els.fileInput.click();
  });
  els.clearFilesButton.addEventListener("click", () => {
    state.selectedFiles = [];
    els.fileInput.value = "";
    els.attachMenu.hidden = true;
    renderSelectedFiles();
  });
  els.fileInput.addEventListener("change", () => addFiles(Array.from(els.fileInput.files || [])));
  els.topicInput.addEventListener("input", autoResizeTopic);

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".attach-wrap")) {
      els.attachMenu.hidden = true;
    }
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    els.promptDropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      els.promptDropZone.classList.add("dragging");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    els.promptDropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      els.promptDropZone.classList.remove("dragging");
    });
  });
  els.promptDropZone.addEventListener("drop", (event) => {
    addFiles(Array.from(event.dataTransfer.files || []));
  });

  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tab));
  });

  document.querySelectorAll("[data-review-decision]").forEach((button) => {
    button.addEventListener("click", () => submitReview(button.dataset.reviewDecision));
  });

  autoResizeTopic();
}

async function runResearch() {
  const topic = els.topicInput.value.trim();
  if (!topic) {
    showMessage("Введите тему исследования.");
    return;
  }

  setBusy(true);
  showMessage("");
  setPill(els.qualityPill, "running", "warn");

  try {
    const run = state.selectedFiles.length
      ? await runResearchWithFiles(topic)
      : await runResearchJson(topic);
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

async function runResearchJson(topic) {
  const payload = basePayload(topic);
  const sourceUrls = parseSourceUrls();
  if (sourceUrls.length) {
    payload.source_urls = sourceUrls;
  }
  return api("/research/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

async function runResearchWithFiles(topic) {
  const payload = basePayload(topic);
  const formData = new FormData();
  Object.entries(payload).forEach(([key, value]) => {
    formData.append(key, value);
  });
  formData.append("source_urls", parseSourceUrls().join("\n"));
  state.selectedFiles.forEach((file) => formData.append("files", file));

  const run = await api("/research/run-with-files", {
    method: "POST",
    body: formData,
  });
  return run;
}

function basePayload(topic) {
  const payload = {
    topic,
    use_live_fetch: els.liveFetchInput.checked,
    actor_id: els.actorInput.value.trim() || "demo_analyst",
    actor_role: els.actorRoleInput.value,
    auto_discover_sources: els.autoDiscoverInput.checked,
  };
  const fetchLimit = Number(els.fetchLimitInput.value);
  if (Number.isFinite(fetchLimit) && fetchLimit > 0) {
    payload.fetch_limit = fetchLimit;
  }
  const discoveryLimit = Number(els.discoveryLimitInput.value);
  if (Number.isFinite(discoveryLimit) && discoveryLimit > 0) {
    payload.discovery_max_sources = discoveryLimit;
  }
  return payload;
}

async function loadRuns() {
  try {
    const payload = await api("/research/runs");
    const runs = payload.runs || [];
    els.runsCount.textContent = String(runs.length);
    els.runsList.innerHTML = "";

    if (!runs.length) {
      els.runsList.innerHTML = '<p class="muted">Пока нет запусков.</p>';
      return;
    }

    runs.slice(0, 30).forEach((run) => {
      const mode = run.evaluation_summary?.source_mode || "auto_discovery";
      const button = document.createElement("button");
      button.type = "button";
      button.className = `run-item ${run.run_id === state.currentRunId ? "active" : ""}`;
      button.innerHTML = `
        <strong>${escapeHtml(run.topic || "Research run")}</strong>
        <span>${escapeHtml(run.quality_gate)} / ${escapeHtml(mode)}</span>
        <small>${escapeHtml(run.run_id)}</small>
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
    els.reportOutput.innerHTML = renderMarkdown(report.markdown || "");
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

  if (run.links.graph) {
    const graph = await api(run.links.graph);
    renderGraph(graph.graph || {});
  } else {
    renderGraph({});
  }

  renderReview(run.review || {});
  renderAuditSnapshot(run);
}

async function submitReview(decision) {
  if (!state.currentRunId) {
    showMessage("Сначала выберите запуск.");
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
  const sourceMode = run.evaluation_summary?.source_mode || "auto_discovery";

  els.runIdValue.textContent = run.run_id || "-";
  els.statusValue.textContent = run.status || "-";
  els.modelValue.textContent = [model.provider, model.model].filter(Boolean).join(" / ") || "-";
  els.sourcesValue.textContent = `${sourcePolicy.allowed_source_count ?? "-"} / ${sourceMode}`;

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
      <td>${formatScore(item.trust_score)}</td>
      <td>${escapeHtml(trimText(item.text || "", 360))}</td>
    `;
    els.evidenceTable.appendChild(row);
  });
  if (!items.length) {
    els.evidenceTable.innerHTML = '<tr><td colspan="6">No evidence loaded.</td></tr>';
  }
}

function renderClaims(items) {
  els.claimsTable.innerHTML = "";
  items.forEach((item) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(item.claim_id || "-")}</td>
      <td>${escapeHtml(item.confidence || "-")}</td>
      <td>${escapeHtml(item.status || "-")}</td>
      <td>${escapeHtml((item.evidence_ids || []).join(", "))}</td>
      <td>${escapeHtml(trimText(item.claim_text || "", 360))}</td>
    `;
    els.claimsTable.appendChild(row);
  });
  if (!items.length) {
    els.claimsTable.innerHTML = '<tr><td colspan="5">No claims loaded.</td></tr>';
  }
}

function renderGraph(graph) {
  const summary = graph.summary || {};
  els.graphSummary.innerHTML = `
    <span class="graph-pill">sources: ${summary.source_count ?? 0}</span>
    <span class="graph-pill">evidence: ${summary.evidence_count ?? 0}</span>
    <span class="graph-pill">claims: ${summary.claim_count ?? 0}</span>
    <span class="graph-pill">links: ${summary.edge_count ?? 0}</span>
  `;
  const sourceSummaries = graph.source_summaries || [];
  els.graphList.innerHTML = "";
  sourceSummaries.slice(0, 8).forEach((source) => {
    const item = document.createElement("div");
    item.className = "graph-item";
    item.innerHTML = `
      <strong>${escapeHtml(source.source_id)}</strong>
      <span>${escapeHtml((source.research_blocks || []).join(", "))}</span>
      <small>${source.evidence_count} evidence</small>
    `;
    els.graphList.appendChild(item);
  });
  if (!sourceSummaries.length) {
    els.graphList.innerHTML = '<p class="muted">Связи появятся после извлечения evidence.</p>';
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
    request_settings: run.request_settings,
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
  const requestOptions = {...options};
  if (!(options.body instanceof FormData)) {
    requestOptions.headers = {"Content-Type": "application/json", ...(options.headers || {})};
  }
  const response = await fetch(path, requestOptions);
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (error) {
    data = {detail: text};
  }
  if (!response.ok) {
    throw new Error(data.detail || `Request failed: ${response.status}`);
  }
  return data;
}

function addFiles(files) {
  const allowed = new Set(["md", "txt", "pdf", "html", "htm"]);
  const accepted = files.filter((file) => {
    const extension = file.name.split(".").pop().toLowerCase();
    return allowed.has(extension);
  });
  const byName = new Map(state.selectedFiles.map((file) => [file.name, file]));
  accepted.forEach((file) => byName.set(file.name, file));
  state.selectedFiles = Array.from(byName.values());
  renderSelectedFiles();
  if (files.length !== accepted.length) {
    showMessage("Часть файлов пропущена: поддерживаются .md, .txt, .pdf, .html.");
  }
}

function renderSelectedFiles() {
  els.selectedFiles.innerHTML = "";
  state.selectedFiles.forEach((file, index) => {
    const chip = document.createElement("span");
    chip.className = "file-chip";
    chip.innerHTML = `
      ${escapeHtml(file.name)}
      <button type="button" title="Удалить файл" aria-label="Удалить файл">×</button>
    `;
    chip.querySelector("button").addEventListener("click", () => {
      state.selectedFiles.splice(index, 1);
      renderSelectedFiles();
    });
    els.selectedFiles.appendChild(chip);
  });
}

function toggleAttachMenu() {
  els.attachMenu.hidden = !els.attachMenu.hidden;
}

function parseSourceUrls() {
  return els.sourceUrlsInput.value
    .split(/\n|,/)
    .map((value) => value.trim())
    .filter(Boolean);
}

function setBusy(isBusy) {
  els.runButton.disabled = isBusy;
  els.runButton.textContent = isBusy ? "Анализ..." : "Запустить";
  els.promptDropZone.classList.toggle("is-loading", isBusy);
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

function autoResizeTopic() {
  els.topicInput.style.height = "auto";
  els.topicInput.style.height = `${Math.min(180, els.topicInput.scrollHeight)}px`;
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

function renderMarkdown(src) {
  const escapeHtml = (s) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) => {
    let t = escapeHtml(s);
    t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
    t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    t = t.replace(/(^|[\s(])((?:https?:\/\/)[^\s<)]+)/g,
      '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
    return t;
  };
  const lines = String(src).replace(/\r\n/g, "\n").split("\n");
  const out = []; let inList = false; let para = [];
  const closeList = () => { if (inList) { out.push("</ul>"); inList = false; } };
  const flushPara = () => { if (para.length) { out.push("<p>" + inline(para.join(" ")) + "</p>"); para = []; } };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (heading) { flushPara(); closeList(); const lvl = heading[1].length;
      out.push("<h" + lvl + ">" + inline(heading[2]) + "</h" + lvl + ">"); }
    else if (bullet) { flushPara(); if (!inList) { out.push("<ul>"); inList = true; }
      out.push("<li>" + inline(bullet[1]) + "</li>"); }
    else if (line.trim() === "") { flushPara(); closeList(); }
    else { para.push(line.trim()); }
  }
  flushPara(); closeList();
  return out.join("\n");
}
