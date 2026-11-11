// CDC Pipeline Dashboard Interactive Controller
const API_BASE = "";

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initEventListeners();
  loadAllData();

  // Auto refresh summary every 30 seconds
  setInterval(loadDashboardSummary, 30000);
});

// --------------------------------------------------------------------
// Tab Switching
// --------------------------------------------------------------------
function initTabs() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");

      tabBtns.forEach(b => b.classList.remove("active"));
      tabPanes.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetPane = document.getElementById(targetId);
      if (targetPane) {
        targetPane.classList.add("active");
      }

      // Contextual refresh on tab switch
      if (targetId === "tab-customers") loadCustomers();
      if (targetId === "tab-quarantine") loadQuarantine();
      if (targetId === "tab-reconciliation") loadReconciliation();
      if (targetId === "tab-history") {
        const custId = document.getElementById("history-cust-id").value;
        if (custId) loadCustomerHistory(custId);
      }
    });
  });
}

// --------------------------------------------------------------------
// Event Listeners
// --------------------------------------------------------------------
function initEventListeners() {
  document.getElementById("btn-refresh-all").addEventListener("click", () => {
    loadAllData();
  });

  // 1. Run Starter Ingestion
  document.getElementById("btn-run-starter").addEventListener("click", async () => {
    const btn = document.getElementById("btn-run-starter");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Ingesting Starter Sample...`;

    try {
      const res = await fetch(`${API_BASE}/api/generator/starter?auto_ingest=true`, { method: "POST" });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`HTTP ${res.status}: ${errText}`);
      }
      const data = await res.json();
      const p = data.pipeline_run || {};
      alert(`Starter Sample Ingested!\nTotal Events: ${data.event_count}\nStatus: ${p.status || 'SUCCESS'}\nInserted: ${p.inserted_count || 0}\nDuplicates: ${p.duplicate_count || 0}\nQuarantined: ${p.quarantined_count || 0}`);
      loadAllData();
    } catch (err) {
      alert("Error ingesting starter: " + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-flask"></i> Generate & Ingest Starter Sample`;
    }
  });

  // 2. Run Scalable Ingestion
  document.getElementById("btn-run-scalable").addEventListener("click", async () => {
    const btn = document.getElementById("btn-run-scalable");
    const count = parseInt(document.getElementById("select-volume").value, 10);
    const seed = parseInt(document.getElementById("input-seed").value, 10) || 42;

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Processing ${count.toLocaleString()} Events...`;

    try {
      const res = await fetch(`${API_BASE}/api/generator/scalable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ total_count: count, seed: seed, auto_ingest: true })
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`HTTP ${res.status}: ${errText}`);
      }
      const data = await res.json();
      const p = data.pipeline_run || {};
      alert(`Scalable Ingestion Completed!\nEvents: ${data.event_count.toLocaleString()}\nStatus: ${p.status || 'SUCCESS'}\nDuration: ${p.duration_ms || 0} ms`);
      loadAllData();
    } catch (err) {
      alert("Error in scalable run: " + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-forward"></i> Ingest Scalable Batch`;
    }
  });

  // 3. Rerun Starter (Idempotency Test)
  document.getElementById("btn-rerun-starter").addEventListener("click", async () => {
    const btn = document.getElementById("btn-rerun-starter");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Rerunning Batch...`;

    try {
      const res = await fetch(`${API_BASE}/api/pipeline/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          batch_name: "rerun_starter_idempotency_test",
          source_file: "starter_sample.json"
        })
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`HTTP ${res.status}: ${errText}`);
      }
      const data = await res.json();
      alert(`Idempotent Rerun Results:\nTotal Events: ${data.total_events}\nNew Inserts: ${data.inserted_count} (Expected: 0)\nDuplicates Identified & Safely Skipped: ${data.duplicate_count}`);
      loadAllData();
    } catch (err) {
      alert("Error rerunning starter: " + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-repeat"></i> Rerun Starter Batch (Verify 0 Duplicates)`;
    }
  });

  // 4. Single Event Simulator
  document.getElementById("btn-send-sim-event").addEventListener("click", async () => {
    const rawText = document.getElementById("cdc-event-input").value;
    const msg = document.getElementById("sim-result-msg");
    msg.textContent = "Processing event...";

    try {
      const eventObj = JSON.parse(rawText);
      const res = await fetch(`${API_BASE}/api/pipeline/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          batch_name: "single_simulator_event",
          events: [eventObj]
        })
      });
      const data = await res.json();
      if (data.inserted_count > 0) {
        msg.innerHTML = `<span style="color:#34d399;"><i class="fa-solid fa-check"></i> Inserted into current state!</span>`;
      } else if (data.updated_count > 0) {
        msg.innerHTML = `<span style="color:#60a5fa;"><i class="fa-solid fa-pen"></i> Updated current state!</span>`;
      } else if (data.deleted_count > 0) {
        msg.innerHTML = `<span style="color:#f87171;"><i class="fa-solid fa-trash"></i> Marked as deleted!</span>`;
      } else if (data.duplicate_count > 0) {
        msg.innerHTML = `<span style="color:#fbbf24;"><i class="fa-solid fa-copy"></i> Idempotent duplicate skipped!</span>`;
      } else if (data.quarantined_count > 0) {
        msg.innerHTML = `<span style="color:#ef4444;"><i class="fa-solid fa-ban"></i> Rejected & Quarantined!</span>`;
      } else if (data.out_of_order_count > 0) {
        msg.innerHTML = `<span style="color:#fbbf24;"><i class="fa-solid fa-clock"></i> Out-of-order: preserved in history only!</span>`;
      }
      loadAllData();
    } catch (err) {
      msg.innerHTML = `<span style="color:#ef4444;">Error: ${err.message}</span>`;
    }
  });

  // 5. Customer History Search
  document.getElementById("btn-fetch-history").addEventListener("click", () => {
    const custId = document.getElementById("history-cust-id").value.trim();
    if (custId) loadCustomerHistory(custId);
  });

  // 6. Customer Search Filter
  let searchTimeout = null;
  document.getElementById("cust-search").addEventListener("input", (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      loadCustomers(e.target.value.trim());
    }, 300);
  });

  // 7. Retry Quarantine
  document.getElementById("btn-retry-quarantine").addEventListener("click", async () => {
    const btn = document.getElementById("btn-retry-quarantine");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Retrying...`;

    try {
      const res = await fetch(`${API_BASE}/api/quarantine/retry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ retry_all: true })
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`HTTP ${res.status}: ${errText}`);
      }
      const data = await res.json();
      alert(`Quarantine Retry Results:\n${data.message}\nResolved: ${data.resolved}\nStill Failing: ${data.still_failing}`);
      loadQuarantine();
      loadDashboardSummary();
    } catch (err) {
      alert("Error retrying quarantine: " + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-rotate-right"></i> Retry All Quarantined Events`;
    }
  });

  // 8. Refresh Reconciliation
  document.getElementById("btn-refresh-recon").addEventListener("click", () => {
    loadReconciliation();
  });
}

// --------------------------------------------------------------------
// Data Loaders
// --------------------------------------------------------------------
async function loadAllData() {
  await Promise.all([
    loadDashboardSummary(),
    loadPipelineRuns(),
    loadCustomers(),
    loadOrders(),
    loadQuarantine(),
    loadReconciliation()
  ]);
}

async function loadDashboardSummary() {
  try {
    const res = await fetch(`${API_BASE}/api/analytics/summary`);
    const d = await res.json();

    document.getElementById("kpi-processed").textContent = (d.total_processed_events || 0).toLocaleString();
    document.getElementById("kpi-customers").textContent = (d.active_customers || 0).toLocaleString();
    document.getElementById("kpi-orders").textContent = (d.active_orders || 0).toLocaleString();
    document.getElementById("kpi-history").textContent = (d.audit_history_records || 0).toLocaleString();
    document.getElementById("kpi-quarantine").textContent = (d.quarantined_records || 0).toLocaleString();
    document.getElementById("kpi-runs").textContent = (d.total_runs || 0).toLocaleString();

    const reconBadge = document.getElementById("recon-badge");
    if (d.all_runs_balanced && d.data_integrity_pass) {
      reconBadge.className = "badge badge-success";
      reconBadge.innerHTML = `<i class="fa-solid fa-shield-check"></i> Invariants: Balanced`;
    } else {
      reconBadge.className = "badge badge-danger";
      reconBadge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Invariants: Discrepancy`;
    }
  } catch (err) {
    console.error("Failed loading summary:", err);
  }
}

async function loadPipelineRuns() {
  const tbody = document.querySelector("#table-pipeline-runs tbody");
  try {
    const res = await fetch(`${API_BASE}/api/pipeline/runs?limit=20`);
    const runs = await res.json();

    if (!runs || runs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="12" class="text-center text-muted">No pipeline runs recorded yet. Click "Generate & Ingest Starter Sample" above.</td></tr>`;
      return;
    }

    tbody.innerHTML = runs.map(r => {
      let statusBadge = "badge-info";
      if (r.status === "SUCCESS") statusBadge = "badge-success";
      else if (r.status === "PARTIAL_SUCCESS") statusBadge = "badge-warning";
      else if (r.status === "FAILED") statusBadge = "badge-danger";

      const started = r.started_at ? r.started_at.split(".")[0].replace("T", " ") : "-";

      return `
        <tr>
          <td><code>${r.run_id}</code></td>
          <td><strong>${escapeHtml(r.batch_name)}</strong></td>
          <td>${started}</td>
          <td>${r.duration_ms != null ? r.duration_ms + ' ms' : '-'}</td>
          <td><span class="badge ${statusBadge}">${r.status}</span></td>
          <td><strong>${r.total_events}</strong></td>
          <td style="color:#34d399;">+${r.inserted_count}</td>
          <td style="color:#60a5fa;">${r.updated_count}</td>
          <td style="color:#f87171;">${r.deleted_count}</td>
          <td style="color:#fbbf24;">${r.duplicate_count}</td>
          <td style="color:#a78bfa;">${r.out_of_order_count}</td>
          <td style="color:#ef4444;">${r.quarantined_count}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="12" class="text-center text-muted">Error loading runs: ${err.message}</td></tr>`;
  }
}

async function loadCustomers(search = "") {
  const tbody = document.querySelector("#table-customers-current tbody");
  try {
    let url = `${API_BASE}/api/customers/current?limit=50`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const res = await fetch(url);
    const customers = await res.json();

    if (!customers || customers.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted">No current customer records found.</td></tr>`;
      return;
    }

    tbody.innerHTML = customers.map(c => {
      let tierBadge = "badge-info";
      if (c.tier === "PLATINUM") tierBadge = "badge-purple";
      else if (c.tier === "GOLD") tierBadge = "badge-warning";
      else if (c.tier === "SILVER") tierBadge = "badge-success";

      let statusBadge = c.is_deleted ? "badge-danger" : (c.status === "ACTIVE" ? "badge-success" : "badge-warning");
      const statusText = c.is_deleted ? "DELETED" : c.status;

      return `
        <tr>
          <td><code>${c.customer_id}</code></td>
          <td><strong>${escapeHtml(c.name)}</strong></td>
          <td>${escapeHtml(c.email)}</td>
          <td><span class="badge ${tierBadge}">${c.tier}</span></td>
          <td>$${Number(c.credit_limit).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
          <td><span class="badge ${statusBadge}">${statusText}</span></td>
          <td>${escapeHtml(c.address_city || '-')}, ${escapeHtml(c.address_country || '-')}</td>
          <td>#${c.last_sequence_number}</td>
          <td>${c.last_event_timestamp.replace('T', ' ').split('.')[0]}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="viewCustomerHistory('${c.customer_id}')">
              <i class="fa-solid fa-timeline"></i> History
            </button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted">Error loading customers: ${err.message}</td></tr>`;
  }
}

async function loadOrders() {
  const tbody = document.querySelector("#table-orders-current tbody");
  try {
    const res = await fetch(`${API_BASE}/api/orders/current?limit=50`);
    const orders = await res.json();

    if (!orders || orders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">No current order records found.</td></tr>`;
      return;
    }

    tbody.innerHTML = orders.map(o => {
      let badge = "badge-info";
      if (o.order_status === "SHIPPED") badge = "badge-success";
      else if (o.order_status === "CANCELLED") badge = "badge-danger";
      else if (o.order_status === "CONFIRMED") badge = "badge-purple";

      return `
        <tr>
          <td><code>${o.order_id}</code></td>
          <td><code>${o.customer_id}</code></td>
          <td><strong>$${Number(o.order_amount).toFixed(2)}</strong></td>
          <td><span class="badge ${badge}">${o.order_status}</span></td>
          <td>${o.currency}</td>
          <td>#${o.last_sequence_number}</td>
          <td>${o.last_event_timestamp.replace('T', ' ').split('.')[0]}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Error loading orders: ${err.message}</td></tr>`;
  }
}

window.viewCustomerHistory = function(customerId) {
  document.getElementById("history-cust-id").value = customerId;
  const historyTabBtn = document.querySelector(`[data-tab="tab-history"]`);
  if (historyTabBtn) historyTabBtn.click();
  loadCustomerHistory(customerId);
};

async function loadCustomerHistory(customerId) {
  const container = document.getElementById("timeline-container");
  container.innerHTML = `<p class="text-center text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Fetching audit history for ${customerId}...</p>`;

  try {
    const res = await fetch(`${API_BASE}/api/customers/history/${encodeURIComponent(customerId)}`);
    const history = await res.json();

    if (!history || history.length === 0) {
      container.innerHTML = `<p class="text-center text-muted">No history found for customer ID: <code>${customerId}</code></p>`;
      return;
    }

    container.innerHTML = history.map((h, idx) => {
      let markerClass = "green";
      if (h.operation === "UPDATE") markerClass = "blue";
      if (h.operation === "DELETE") markerClass = "red";
      if (h.is_out_of_order) markerClass = "orange";

      const validFrom = h.valid_from ? h.valid_from.replace("T", " ").split(".")[0] : "-";
      const validTo = h.valid_to ? h.valid_to.replace("T", " ").split(".")[0] : "<span class='badge badge-success'>CURRENT EFFECTIVE</span>";

      return `
        <div class="timeline-item ${h.is_current ? 'active-version' : ''} ${h.is_out_of_order ? 'out-of-order' : ''}">
          <div class="timeline-marker ${markerClass}"></div>
          <div class="timeline-header">
            <div>
              <strong>Sequence #${h.sequence_number}</strong> — <span class="badge ${h.operation === 'INSERT' ? 'badge-success' : (h.operation === 'UPDATE' ? 'badge-info' : 'badge-danger')}">${h.operation}</span>
              ${h.is_current ? '<span class="badge badge-success">ACTIVE VERSION</span>' : ''}
              ${h.is_out_of_order ? '<span class="badge badge-warning"><i class="fa-solid fa-clock"></i> OUT-OF-ORDER</span>' : ''}
            </div>
            <div class="text-muted" style="font-size:12px;">Event TS: ${h.event_timestamp.replace("T", " ").split(".")[0]}</div>
          </div>
          <div style="font-size:13px; line-height:1.6;">
            <div><strong>Name:</strong> ${escapeHtml(h.name)} &nbsp;|&nbsp; <strong>Email:</strong> ${escapeHtml(h.email)}</div>
            <div><strong>Tier:</strong> ${h.tier} &nbsp;|&nbsp; <strong>Credit Limit:</strong> $${Number(h.credit_limit).toLocaleString()} &nbsp;|&nbsp; <strong>Status:</strong> ${h.status}</div>
            <div class="text-muted mt-2" style="font-size:12px;">
              <strong>Validity Period:</strong> <code>${validFrom}</code> &rarr; <code>${validTo}</code>
              &nbsp;|&nbsp; <strong>Pipeline Run:</strong> <code>${h.pipeline_run_id}</code>
            </div>
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    container.innerHTML = `<p class="text-center text-muted">Error loading history: ${err.message}</p>`;
  }
}

async function loadQuarantine() {
  const tbody = document.querySelector("#table-quarantine tbody");
  try {
    const res = await fetch(`${API_BASE}/api/quarantine?limit=50`);
    const items = await res.json();

    if (!items || items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Dead-letter queue is empty! No rejected events.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map(q => {
      let badge = "badge-danger";
      if (q.status === "RESOLVED") badge = "badge-success";
      if (q.status === "RETRIED") badge = "badge-warning";

      let errorBadge = "badge-danger";
      if (q.error_code === "REFERENTIAL_INTEGRITY_VIOLATION") errorBadge = "badge-purple";
      else if (q.error_code === "BUSINESS_RULE_VIOLATION") errorBadge = "badge-warning";

      return `
        <tr>
          <td>#${q.quarantine_id}</td>
          <td><code>${q.pipeline_run_id}</code></td>
          <td><strong>${escapeHtml(q.entity_type || '-')}</strong> (${escapeHtml(q.entity_id || '-')})</td>
          <td><span class="badge ${errorBadge}">${q.error_code}</span></td>
          <td style="color:#f87171; max-width:250px;">${escapeHtml(q.error_message)}</td>
          <td>${q.quarantined_at.replace('T', ' ').split('.')[0]}</td>
          <td><span class="badge ${badge}">${q.status} (Retries: ${q.retry_count})</span></td>
          <td>
            <details>
              <summary style="cursor:pointer; color:#38bdf8; font-size:12px;">View Payload</summary>
              <pre style="background:#0b1120; padding:6px; font-size:11px; max-width:300px; overflow-x:auto;">${escapeHtml(q.raw_payload)}</pre>
            </details>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Error loading quarantine: ${err.message}</td></tr>`;
  }
}

async function loadReconciliation() {
  const summaryBox = document.getElementById("recon-summary-text");
  const runsTable = document.querySelector("#table-recon-runs tbody");

  try {
    const res = await fetch(`${API_BASE}/api/reconciliation/report`);
    const r = await res.json();

    document.getElementById("val-dup-pk").textContent = r.duplicate_primary_keys_detected;
    document.getElementById("val-scd2").textContent = r.scd2_multiple_active_violations;
    document.getElementById("val-ref").textContent = r.referential_integrity_violations;

    if (r.all_runs_balanced) {
      summaryBox.innerHTML = `
        <span style="color:#34d399; font-weight:600;"><i class="fa-solid fa-circle-check"></i> ALL PIPELINE RUNS PERFECTLY BALANCED:</span>
        Total Input (${r.total_source_events.toLocaleString()}) = Mutations (${r.total_successful_mutations.toLocaleString()}) + Deduplicated (${r.total_deduplicated_events.toLocaleString()}) + Out-of-Order (${r.total_out_of_order_events.toLocaleString()}) + Quarantined (${r.total_quarantined_records.toLocaleString()}).
      `;
    } else {
      summaryBox.innerHTML = `
        <span style="color:#ef4444; font-weight:600;"><i class="fa-solid fa-triangle-exclamation"></i> UNBALANCED RUNS DETECTED:</span>
        Run IDs: ${r.unbalanced_run_ids.join(', ')}
      `;
    }

    if (!r.details || r.details.length === 0) {
      runsTable.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No runs available to reconcile.</td></tr>`;
      return;
    }

    runsTable.innerHTML = r.details.map(d => {
      const delta = d.total_events - d.sum_parts;
      const isBalanced = d.is_balanced === 1;

      return `
        <tr>
          <td><code>${d.run_id}</code></td>
          <td><strong>${escapeHtml(d.batch_name)}</strong></td>
          <td>${d.total_events.toLocaleString()}</td>
          <td>${d.sum_parts.toLocaleString()}</td>
          <td>${delta === 0 ? '<span style="color:#34d399;">0 (Exact Match)</span>' : '<span style="color:#ef4444;">' + delta + '</span>'}</td>
          <td>
            <span class="badge ${isBalanced ? 'badge-success' : 'badge-danger'}">
              <i class="fa-solid ${isBalanced ? 'fa-check' : 'fa-xmark'}"></i> ${isBalanced ? 'BALANCED' : 'DISCREPANCY'}
            </span>
          </td>
        </tr>
      `;
    }).join("");

  } catch (err) {
    summaryBox.textContent = "Error running reconciliation: " + err.message;
  }
}

function escapeHtml(text) {
  if (text == null) return "";
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}
