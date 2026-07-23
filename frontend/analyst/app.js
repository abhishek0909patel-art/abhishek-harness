const $ = (sel) => document.querySelector(sel);
const els = {
 files: $('#files'),
 uploadStatus: $('#upload-status'),
 datasetList: $('#dataset-list'),
 schemaText: $('#schema-text'),
 auditList: $('#audit-list'),
 chat: $('#chat'),
 suggestions: $('#suggestions'),
 resultTable: $('#result-table'),
 chart: $('#chart'),
 resultText: $('#result-text'),
 officer: $('#officer'),
 chatForm: $('#chat-form'),
 chatInput: $('#chat-input'),
 chatSubmit: $('#chat-submit'),
 loadingOverlay: $('#loading-overlay'),
 errorBanner: $('#error-banner'),
 errorMessage: $('#error-message'),
 errorDismiss: $('#error-dismiss'),
 statusBadge: $('#status-badge'),
};

function setStatus(status, ok = true) {
 if (!els.statusBadge) return;
 els.statusBadge.textContent = status;
 els.statusBadge.className = ok ? 'badge badge-ok' : 'badge';
}
function showLoading() {
 els.loadingOverlay?.classList.remove('hidden');
 setStatus('Running…', true);
}
function hideLoading() {
 els.loadingOverlay?.classList.add('hidden');
 setStatus('Ready', true);
}
function showError(msg) {
 if (!els.errorBanner || !els.errorMessage) return;
 els.errorMessage.textContent = msg || 'Something went wrong.';
 els.errorBanner.classList.remove('hidden');
 setStatus('Error', false);
}
function dismissError() {
 els.errorBanner?.classList.add('hidden');
 setStatus('Ready', true);
}
function setRoleDisplay() {
 const officer = (els.officer?.value || '').trim();
 const roleDisplay = document.getElementById('role-display');
 if (!roleDisplay) return;
 roleDisplay.textContent = officer ? `Role: Officer (${officer})` : 'Role: Not set';
}
function addAudit(entry) {
 if (!els.auditList) return;
 const li = document.createElement('li');
 li.textContent = `${new Date(entry.timestamp).toLocaleTimeString()} — ${entry.query} — ${entry.status}`;
 els.auditList.prepend(li);
}
function addTurn(role, html) {
 const div = document.createElement('div');
 div.className = `turn ${role}`;
 div.innerHTML = html;
 els.chat.appendChild(div);
 els.chat.scrollTop = els.chat.scrollHeight;
}
function renderTable(table, columns) {
 if (!table || !columns) return;
 const thead = '<thead><tr>' + columns.map(c => `<th>${c}</th>`).join('') + '</tr></thead>';
 const tbody = '<tbody>' + table.map(row => '<tr>' + columns.map(c => `<td>${row[c] ?? ''}</td>`).join('') + '</tr>').join('') + '</tbody>';
 els.resultTable.innerHTML = thead + tbody;
}
function renderChart(spec) {
 if (!spec) { els.chart.innerHTML = ''; return; }
 const host = document.createElement('div');
 host.id = 'chart-host';
 host.style.width = '100%';
 host.style.height = '360px';
 els.chart.innerHTML = '';
 els.chart.appendChild(host);
 if (window.Plotly) {
  Plotly.newPlot(host, spec.data || [], spec.layout || {}, { responsive: true, displayModeBar: true });
 } else {
  host.innerHTML = '<pre class="result-text">' + JSON.stringify(spec, null, 2) + '</pre>';
 }
}
async function upload() {
 if (!els.files?.files?.length) return;
 const fd = new FormData();
 Array.from(els.files.files).forEach((f) => fd.append('files', f));
 els.uploadStatus.textContent = 'Uploading…';
 try {
  const res = await fetch('/api/v1/analyst/upload', { method: 'POST', body: fd });
  if (!res.ok) {
   els.uploadStatus.textContent = await res.text();
   showError('Upload failed. Check the file format and try again.');
   return;
  }
  const datasets = await res.json();
  els.uploadStatus.textContent = `Loaded ${datasets.length} file(s)`;
  els.datasetList.innerHTML = '';
  datasets.forEach((d) => {
   const li = document.createElement('li');
   li.textContent = `${d.filename} (${d.row_count} rows)`;
   li.onclick = async () => {
    const r = await fetch(`/api/v1/analyst/schema/${encodeURIComponent(d.filename)}`);
    const j = await r.json();
    els.schemaText.textContent = j.columns.map((c) => `${c.name} (${c.dtype})`).join('\n');
   };
   els.datasetList.appendChild(li);
  });
  addTurn('agent', 'Datasets ready. Ask me anything about the data.');
 } catch (err) {
  showError('Upload failed due to a network error.');
 }
}
async function ask(question) {
 if (!question) return;
 addTurn('officer', question);
 els.suggestions.innerHTML = '';
 els.resultText.textContent = 'Running…';
 showLoading();
 try {
  const res = await fetch('/api/v1/analyst/query', {
   method: 'POST',
   headers: { 'Content-Type': 'application/json' },
   body: JSON.stringify({ question }),
  });
  const data = await res.json();
  if (!res.ok || data.error) {
   throw new Error(data.error || `Request failed with status ${res.status}`);
  }
  addTurn('agent', `<pre>${data.output_text || ''}</pre>`);
  renderTable(data.output_table, data.output_columns);
  renderChart(data.output_chart);
  els.resultText.textContent = data.output_text || '';
  if (data.followups?.length) {
   els.suggestions.innerHTML = data.followups.map((f) => `<button class="chip">${f}</button>`).join('');
   els.suggestions.querySelectorAll('.chip').forEach((btn) => {
    btn.onclick = () => ask(btn.textContent);
   });
  }
  addAudit({ timestamp: new Date().toISOString(), query: question, status: data.status || 'completed' });
 } catch (err) {
  showError(err.message || 'Query failed.');
  addAudit({ timestamp: new Date().toISOString(), query: question, status: 'failed' });
 } finally {
  hideLoading();
 }
}
function wireEvents() {
 els.files?.addEventListener('change', upload);
 els.errorDismiss?.addEventListener('click', dismissError);
 els.officer?.addEventListener('input', setRoleDisplay);
 if (els.chatForm && els.chatInput) {
  els.chatForm.addEventListener('submit', (e) => {
   e.preventDefault();
   const question = els.chatInput.value.trim();
   if (!question) return;
   ask(question);
   els.chatInput.value = '';
  });
  els.chatSubmit?.addEventListener('click', () => {
   const question = els.chatInput?.value?.trim() || '';
   if (!question) return;
   ask(question);
   els.chatInput.value = '';
  });
 }
 if (els.chatInput) {
  els.chatInput.addEventListener('keydown', (e) => {
   if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    const question = els.chatInput.value.trim();
    if (question) {
     ask(question);
     els.chatInput.value = '';
    }
   }
  });
 }
}
wireEvents();
setRoleDisplay();
