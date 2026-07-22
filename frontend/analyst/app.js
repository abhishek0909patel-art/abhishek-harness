const $ = (sel) => document.querySelector(sel);
const els = {
  files: $('#files'),
  uploadStatus: $('#upload-status'),
  datasetList: $('#dataset-list'),
  schemaText: $('#schema-text'),
  auditList: $('#audit-list'),
  chat: $('#chat'),
  suggestions: $('#suggestions'),
  code: $('#code'),
  rerun: $('#rerun'),
  copy: $('#copy'),
  resultTable: $('#result-table'),
  chart: $('#chart'),
  resultText: $('#result-text'),
  officer: $('#officer'),
};

function addAudit(entry) {
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
  const thead = '<tr>' + columns.map(c => `<th>${c}</th>`).join('') + '</tr>';
  const tbody = table.map(row => '<tr>' + columns.map(c => `<td>${row[c] ?? ''}</td>`).join('') + '</tr>').join('');
  els.resultTable.innerHTML = thead + tbody;
}
function renderChart(spec) {
  if (!spec) { els.chart.innerHTML = ''; return; }
  const data = JSON.stringify(spec);
  els.resultTable.insertAdjacentHTML('afterend', `<div id="chart-host" style="width:100%;height:360px;"></div>`);
  Plotly.newPlot('chart-host', spec.data || [], spec.layout || {}, { responsive: true, displayModeBar: true });
}
async function upload() {
  const fd = new FormData();
  Array.from(els.files.files).forEach((f) => fd.append('files', f));
  els.uploadStatus.textContent = 'Uploading…';
  const res = await fetch('/api/v1/analyst/upload', { method: 'POST', body: fd });
  if (!res.ok) { els.uploadStatus.textContent = await res.text(); return; }
  const datasets = await res.json();
  els.uploadStatus.textContent = `Loaded ${datasets.length} file(s)`;
  datasets.forEach(d => {
    const li = document.createElement('li');
    li.textContent = `${d.filename} (${d.row_count} rows)`;
    li.onclick = async () => {
      const r = await fetch(`/api/v1/analyst/schema/${encodeURIComponent(d.filename)}`);
      const j = await r.json();
      els.schemaText.textContent = j.columns.map(c => `${c.name} (${c.dtype})`).join('\n');
    };
    els.datasetList.appendChild(li);
  });
}
async function ask(question) {
  addTurn('officer', question);
  els.suggestions.innerHTML = '';
  els.resultText.textContent = 'Running…';
  const res = await fetch('/api/v1/analyst/query', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question })
  });
  const data = await res.json();
  addTurn('agent', `<pre>${data.output_text || ''}</pre>`);
  renderTable(data.output_table, data.output_columns);
  if (data.output_chart) renderChart(data.output_chart);
  if (data.error) els.resultText.textContent = data.error; els.resultText.textContent = data.output_text || '';
  els.code.value = data.generated_code || '';
  if (data.followups?.length) {
    els.suggestions.innerHTML = data.followups.map(f => `<button class="chip">${f}</button>`).join('');
    els.suggestions.querySelectorAll('.chip').forEach(btn => btn.onclick = () => ask(btn.textContent));
  }
  addAudit({ timestamp: new Date().toISOString(), query: question, status: data.status || 'failed' });
}
els.files.addEventListener('change', upload);
els.rerun.addEventListener('click', () => { const c = els.code.value; if (c) ask(c); });
els.copy.addEventListener('click', () => { els.code.select(); document.execCommand('copy'); });
