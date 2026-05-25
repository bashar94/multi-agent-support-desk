const state = {
  samples: [],
  tickets: [],
  result: null,
  activeTab: "reply",
};

const elements = {
  serviceStatus: document.querySelector("#serviceStatus"),
  refreshButton: document.querySelector("#refreshButton"),
  loadFirstSampleButton: document.querySelector("#loadFirstSampleButton"),
  ticketForm: document.querySelector("#ticketForm"),
  subjectInput: document.querySelector("#subjectInput"),
  emailInput: document.querySelector("#emailInput"),
  messageInput: document.querySelector("#messageInput"),
  analyzeButton: document.querySelector("#analyzeButton"),
  sampleCount: document.querySelector("#sampleCount"),
  sampleList: document.querySelector("#sampleList"),
  ticketCount: document.querySelector("#ticketCount"),
  ticketList: document.querySelector("#ticketList"),
  emptyState: document.querySelector("#emptyState"),
  resultView: document.querySelector("#resultView"),
  resultSubject: document.querySelector("#resultSubject"),
  reanalyzeButton: document.querySelector("#reanalyzeButton"),
  metricStrip: document.querySelector("#metricStrip"),
  agentTrace: document.querySelector("#agentTrace"),
  replyPanel: document.querySelector("#replyPanel"),
  diagnosticPanel: document.querySelector("#diagnosticPanel"),
  knowledgePanel: document.querySelector("#knowledgePanel"),
  jsonPanel: document.querySelector("#jsonPanel"),
  tabs: Array.from(document.querySelectorAll(".tab-button")),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `Request failed with ${response.status}`);
  }
  return data;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatLabel(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function setStatus(label, mode) {
  elements.serviceStatus.textContent = label;
  elements.serviceStatus.className = `status-pill ${mode || ""}`.trim();
}

async function initialize() {
  bindEvents();
  try {
    await api("/api/health");
    setStatus("API Online", "ok");
  } catch (error) {
    setStatus("API Offline", "fail");
  }

  await Promise.all([loadSamples(), loadTickets()]);
  if (state.samples[0]) {
    fillForm(state.samples[0]);
  }
}

function bindEvents() {
  elements.ticketForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await analyzeCurrentTicket();
  });

  elements.refreshButton.addEventListener("click", loadTickets);

  elements.loadFirstSampleButton.addEventListener("click", () => {
    if (state.samples[0]) {
      fillForm(state.samples[0]);
    }
  });

  elements.reanalyzeButton.addEventListener("click", async () => {
    if (!state.result) {
      return;
    }
    elements.reanalyzeButton.disabled = true;
    try {
      const result = await api(`/api/tickets/${state.result.ticket.id}/reanalyze`, { method: "POST" });
      setResult(result);
      await loadTickets();
    } finally {
      elements.reanalyzeButton.disabled = false;
    }
  });

  elements.tabs.forEach((button) => {
    button.addEventListener("click", () => setActiveTab(button.dataset.tab));
  });
}

async function loadSamples() {
  const data = await api("/api/sample-tickets");
  state.samples = data.tickets || [];
  renderSamples();
}

async function loadTickets() {
  const data = await api("/api/tickets");
  state.tickets = data.tickets || [];
  renderTickets();
}

function renderSamples() {
  elements.sampleCount.textContent = state.samples.length;
  elements.sampleList.innerHTML = state.samples
    .map(
      (ticket, index) => `
        <button class="list-item" type="button" data-sample-index="${index}">
          <strong>${escapeHtml(ticket.subject)}</strong>
          <span>${escapeHtml(ticket.customer_email || "sample ticket")}</span>
        </button>
      `
    )
    .join("");

  elements.sampleList.querySelectorAll("[data-sample-index]").forEach((button) => {
    button.addEventListener("click", () => fillForm(state.samples[Number(button.dataset.sampleIndex)]));
  });
}

function renderTickets() {
  elements.ticketCount.textContent = state.tickets.length;
  if (state.tickets.length === 0) {
    elements.ticketList.innerHTML = `<div class="list-item"><strong>No saved tickets</strong><span>Run an analysis first</span></div>`;
    return;
  }

  elements.ticketList.innerHTML = state.tickets
    .map(
      (ticket) => `
        <button class="list-item" type="button" data-ticket-id="${escapeHtml(ticket.id)}">
          <strong>${escapeHtml(ticket.subject)}</strong>
          <span>${escapeHtml(formatLabel(ticket.priority))} / ${escapeHtml(ticket.owner_team)}</span>
        </button>
      `
    )
    .join("");

  elements.ticketList.querySelectorAll("[data-ticket-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const result = await api(`/api/tickets/${button.dataset.ticketId}`);
      setResult(result);
    });
  });
}

function fillForm(ticket) {
  elements.subjectInput.value = ticket.subject || "";
  elements.emailInput.value = ticket.customer_email || "";
  elements.messageInput.value = ticket.message || "";
}

async function analyzeCurrentTicket() {
  const payload = {
    subject: elements.subjectInput.value,
    customer_email: elements.emailInput.value,
    message: elements.messageInput.value,
    source: "dashboard",
  };

  elements.analyzeButton.disabled = true;
  elements.analyzeButton.textContent = "Running";
  try {
    const result = await api("/api/tickets/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setResult(result);
    await loadTickets();
  } finally {
    elements.analyzeButton.disabled = false;
    elements.analyzeButton.textContent = "Run Agents";
  }
}

function setResult(result) {
  state.result = result;
  elements.emptyState.classList.add("hidden");
  elements.resultView.classList.remove("hidden");
  renderResult();
}

function renderResult() {
  const result = state.result;
  if (!result) {
    return;
  }

  elements.resultSubject.textContent = result.ticket.subject;
  renderMetrics(result);
  renderTrace(result.trace || []);
  renderReply(result);
  renderDiagnostic(result);
  renderKnowledge(result);
  elements.jsonPanel.textContent = JSON.stringify(result, null, 2);
  setActiveTab(state.activeTab);
}

function renderMetrics(result) {
  const metrics = [
    ["Priority", result.intake.data.priority, `priority-${result.intake.data.priority}`],
    ["Category", formatLabel(result.intake.data.category), ""],
    ["Owner", result.routing.data.owner_team, ""],
    ["SLA", result.routing.data.sla, ""],
    ["Quality", `${result.quality.data.quality_score}/100`, ""],
  ];

  elements.metricStrip.innerHTML = metrics
    .map(
      ([label, value, className]) => `
        <div class="metric ${escapeHtml(className)}">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `
    )
    .join("");
}

function renderTrace(trace) {
  elements.agentTrace.innerHTML = trace
    .map(
      (step) => `
        <article class="agent-step">
          <strong>${escapeHtml(step.agent)}</strong>
          <p>${escapeHtml(step.summary)}</p>
        </article>
      `
    )
    .join("");
}

function renderReply(result) {
  elements.replyPanel.innerHTML = `
    <div class="reply-text">${escapeHtml(result.response.data.draft)}</div>
  `;
}

function renderDiagnostic(result) {
  const diagnostic = result.diagnostic.data;
  const routing = result.routing.data;
  const quality = result.quality.data;
  elements.diagnosticPanel.innerHTML = `
    <div class="detail-grid">
      ${detailBlock("Likely Cause", diagnostic.likely_cause)}
      ${detailBlock("Customer Impact", diagnostic.customer_impact)}
      ${listBlock("Missing Information", diagnostic.missing_information)}
      ${listBlock("Risk Flags", diagnostic.risk_flags)}
      ${listBlock("Routing Tags", routing.tags)}
      ${listBlock("Quality Checks", Object.entries(quality.checks).map(([key, value]) => `${formatLabel(key)}: ${value ? "pass" : "fail"}`))}
    </div>
  `;
}

function renderKnowledge(result) {
  const matches = result.knowledge.data.matches || [];
  if (!matches.length) {
    elements.knowledgePanel.innerHTML = `<p>No strong knowledge base match found.</p>`;
    return;
  }

  elements.knowledgePanel.innerHTML = `
    <div class="knowledge-list">
      ${matches
        .map(
          (match) => `
            <article class="knowledge-item">
              <h3>${escapeHtml(match.article.title)}</h3>
              <p>${escapeHtml(match.article.content)}</p>
              <p><strong>Score:</strong> ${escapeHtml(match.score)} · <strong>Team:</strong> ${escapeHtml(match.article.team)}</p>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function detailBlock(title, value) {
  return `
    <section class="detail-block">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(value || "None")}</p>
    </section>
  `;
}

function listBlock(title, items) {
  const values = Array.isArray(items) && items.length ? items : ["None"];
  return `
    <section class="detail-block">
      <h3>${escapeHtml(title)}</h3>
      <ul>${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>
  `;
}

function setActiveTab(tab) {
  state.activeTab = tab;
  elements.tabs.forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });

  const panels = {
    reply: elements.replyPanel,
    diagnostic: elements.diagnosticPanel,
    knowledge: elements.knowledgePanel,
    json: elements.jsonPanel,
  };

  Object.entries(panels).forEach(([key, panel]) => {
    panel.classList.toggle("hidden", key !== tab);
  });
}

initialize().catch((error) => {
  setStatus(error.message, "fail");
});
