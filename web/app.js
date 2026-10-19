document.addEventListener('DOMContentLoaded', () => {
  // Tabs
  const navTabs = document.querySelectorAll('.nav-tab');
  const viewPanels = document.querySelectorAll('.view-panel');
  
  navTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      navTabs.forEach(t => t.classList.remove('active'));
      viewPanels.forEach(p => p.classList.remove('active-panel'));
      
      tab.classList.add('active');
      const target = document.getElementById(tab.dataset.tab);
      if (target) target.classList.add('active-panel');
    });
  });

  // Corporate Tenant Toggle
  const sbiBtn = document.getElementById('tenant-sbi-btn');
  const tcsBtn = document.getElementById('tenant-tcs-btn');
  const tenantName = document.getElementById('tenant-name');
  let currentTenant = 'SBI';

  sbiBtn.addEventListener('click', () => {
    currentTenant = 'SBI';
    sbiBtn.classList.add('active');
    tcsBtn.classList.remove('active');
    tenantName.textContent = 'State Bank of India (SBI)';
  });

  tcsBtn.addEventListener('click', () => {
    currentTenant = 'TCS';
    tcsBtn.classList.add('active');
    sbiBtn.classList.remove('active');
    tenantName.textContent = 'Tata Consultancy Services (TCS)';
  });

  // Chat Elements
  const chatMessages = document.getElementById('chat-messages');
  const chatForm = document.getElementById('chat-form');
  const queryInput = document.getElementById('query-input');
  const quickChips = document.querySelectorAll('.quick-chip');

  quickChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const q = chip.dataset.query;
      queryInput.value = q;
      handleSubmitQuery(q);
    });
  });

  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = queryInput.value.trim();
    if (!q) return;
    handleSubmitQuery(q);
  });

  async function handleSubmitQuery(query) {
    appendUserBubble(query);
    queryInput.value = '';

    const loadingId = 'loading-' + Date.now();
    appendLoadingBubble(loadingId);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      });

      if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
      const data = await res.json();
      removeLoadingBubble(loadingId);
      appendAssistantBubble(data);
    } catch (err) {
      removeLoadingBubble(loadingId);
      appendErrorBubble(err.message);
    }
  }

  function appendUserBubble(text) {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble user-bubble';
    bubble.innerHTML = `<div class="bubble-body">${escapeHtml(text)}</div>`;
    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function appendLoadingBubble(id) {
    const bubble = document.createElement('div');
    bubble.id = id;
    bubble.className = 'chat-bubble assistant-bubble';
    bubble.innerHTML = `
      <div class="bubble-header">
        <span class="bubble-avatar">🛡️</span>
        <span class="bubble-name">CorpShield Policy Desk</span>
        <span class="bubble-badge">Validating band entitlement...</span>
      </div>
      <div class="bubble-body" style="color: var(--text-muted); font-style: italic;">
        Checking distance cutoff thresholds, cabin eligibility, and corporate GSTIN matching...
      </div>
    `;
    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function removeLoadingBubble(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function appendErrorBubble(errText) {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble assistant-bubble';
    bubble.innerHTML = `
      <div class="bubble-body" style="background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.3); color: #fca5a5;">
        ⚠️ Error: ${escapeHtml(errText)}
      </div>
    `;
    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function appendAssistantBubble(data) {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble assistant-bubble';

    let packetHtml = '';
    if (data.verdict && data.verdict.approval_packet) {
      const p = data.verdict.approval_packet;
      packetHtml = `
        <div class="approval-packet-card">
          <div class="packet-header">
            <span class="packet-title">📑 Pre-Filled Manager Approval Packet</span>
            <span class="packet-badge">+₹${p.budget_overrun.toFixed(2)} OVERRUN</span>
          </div>
          <div class="packet-body">
            <div><strong>Employee Band:</strong> ${escapeHtml(p.employee_grade)}</div>
            <div><strong>Sector / Route:</strong> ${escapeHtml(p.route)}</div>
            <div><strong>Selected Fare:</strong> ₹${p.selected_fare.toFixed(2)} (Policy Limit: ₹${p.max_allowed_fare.toFixed(2)})</div>
            <div><strong>Exception Grounds:</strong> ${escapeHtml(p.reason_for_exception)}</div>
            <button class="packet-btn" onclick="alert('Approval packet dispatched to reporting authority.')">
              ⚡ Dispatch One-Click Approval Link
            </button>
          </div>
        </div>
      `;
    }

    bubble.innerHTML = `
      <div class="bubble-header">
        <span class="bubble-avatar">🛡️</span>
        <span class="bubble-name">CorpShield Policy Desk</span>
        <span class="bubble-badge">${data.verdict ? data.verdict.verdict : 'GST Validation'}</span>
        <span class="bubble-badge" style="background: rgba(14, 165, 233, 0.2); color: #7dd3fc;">${data.latency_ms.toFixed(1)}ms</span>
      </div>
      <div class="bubble-body">
        <div style="white-space: pre-line; line-height: 1.55;">${formatMarkdown(data.answer)}</div>
        ${packetHtml}
      </div>
    `;

    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // Load Policies Grid
  async function loadPolicies() {
    try {
      const res = await fetch('/api/policies');
      const policies = await res.json();
      renderPolicies(policies);
    } catch (err) {
      console.error('Failed to load policies', err);
    }
  }

  function renderPolicies(policies) {
    const grid = document.getElementById('policies-grid');
    grid.innerHTML = policies.map(p => `
      <div class="policy-card">
        <div class="policy-card-header">
          <div>
            <span class="corp-badge">${escapeHtml(p.corporate_name)}</span>
            <h3 style="font-size: 1.05rem; font-weight: 700; margin-top: 4px;">${escapeHtml(p.grade_group)}</h3>
          </div>
          <span class="policy-citation">${escapeHtml(p.citation)}</span>
        </div>

        <div style="font-size: 0.84rem; color: var(--text-secondary); line-height: 1.5;">
          <div><strong>Air Eligibility:</strong> ${escapeHtml(p.entitlements.air_travel_eligibility)}</div>
          <div><strong>Max Airfare Cap:</strong> ₹${p.entitlements.max_domestic_fare_inr.toFixed(0)}</div>
          <div><strong>Cabin Allowed:</strong> ${escapeHtml(p.entitlements.cabin_class)} (${p.entitlements.business_class_allowed ? 'Business Permitted' : 'Economy Only'})</div>
          <div><strong>Train Alternative:</strong> ${escapeHtml(p.entitlements.train_entitlement)}</div>
          <div><strong>Daily Hotel Allowance:</strong> ₹${p.entitlements.daily_hotel_allowance_tier1.toFixed(0)} (Tier 1) / ₹${p.entitlements.daily_hotel_allowance_other.toFixed(0)} (Others)</div>
        </div>
      </div>
    `).join('');
  }

  // Load Evals
  async function loadEvals() {
    try {
      const res = await fetch('/api/evals');
      const data = await res.json();
      renderEvals(data);
    } catch (err) {
      console.error('Failed to load evals', err);
    }
  }

  function renderEvals(data) {
    document.getElementById('kpi-pass-rate').textContent = `${data.pass_rate_percentage}%`;
    document.getElementById('kpi-compliance').textContent = `${data.policy_compliance_accuracy.toFixed(1)}%`;

    const tbody = document.getElementById('evals-table-body');
    tbody.innerHTML = data.results.map(r => `
      <tr>
        <td style="font-weight: 700; color: white;">${escapeHtml(r.test_id)}</td>
        <td><span class="${r.passed ? 'badge-pass' : 'badge-fail'}">${r.passed ? 'PASS' : 'FAIL'}</span></td>
        <td>${r.verdict_matched ? '✅ Enforced' : '❌ Violation'}</td>
        <td>${r.citation_matched ? '✅ Verified' : '—'}</td>
        <td style="font-family: var(--font-mono);">${r.latency_ms.toFixed(1)}ms</td>
      </tr>
    `).join('');
  }

  // Run Evals Live
  const runEvalsBtn = document.getElementById('run-evals-btn');
  runEvalsBtn.addEventListener('click', async () => {
    runEvalsBtn.disabled = true;
    runEvalsBtn.textContent = '⚡ Running Benchmark...';
    try {
      const res = await fetch('/api/evals/run', { method: 'POST' });
      const fresh = await res.json();
      renderEvals(fresh);
    } catch (err) {
      alert('Error: ' + err.message);
    } finally {
      runEvalsBtn.disabled = false;
      runEvalsBtn.textContent = '⚡ Run Compliance Benchmark';
    }
  });

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag));
  }

  function formatMarkdown(text) {
    if (!text) return '';
    return escapeHtml(text)
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.*?)`/g, '<code style="background: rgba(0,136,204,0.25); color: #7dd3fc; padding: 1px 6px; border-radius: 4px; font-family: monospace;">$1</code>');
  }

  loadPolicies();
  loadEvals();
});
