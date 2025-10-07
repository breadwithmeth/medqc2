(() => {
  const $ = (sel) => document.querySelector(sel);
  const apiBase = window.API_BASE || location.origin;
  $('#apiBase').textContent = apiBase;

  async function audit() {
    const f = $('#file').files[0];
    if (!f) { alert('Выберите PDF-файл'); return; }
    const human = $('#human').checked;
    const format = $('#format').value;

    const fd = new FormData();
    fd.append('file', f);

    const url = new URL('/audit/pdf_stac', apiBase);
    if (human) url.searchParams.set('human', 'true');
    if (human) url.searchParams.set('format', format);

    $('#run').disabled = true;
    $('#dlJson').disabled = true;
    $('#dlMd').disabled = true;
    $('#out').textContent = 'Загрузка и анализ…';
    $('#violBox').hidden = true; $('#violList').innerHTML='';
    $('#diagBox').hidden = true; $('#diag').innerHTML=''; $('#assessed').innerHTML='';

    try {
      const resp = await fetch(url, { method: 'POST', body: fd });
      const ct = resp.headers.get('content-type') || '';
      const text = await resp.text();
      if (!resp.ok) throw new Error(text || resp.statusText);

      if (ct.includes('application/json')) {
        $('#out').textContent = prettyJson(text);
        const obj = JSON.parse(text);
        renderViolations(obj);
        renderDiagnostics(obj);
        enableDownloads(obj);
      } else {
        $('#out').textContent = text; // text/markdown
        enableDownloads(null, text);
      }
    } catch (e) {
      $('#out').textContent = 'Ошибка: ' + e.message;
    } finally {
      $('#run').disabled = false;
    }
  }

  function prettyJson(t) {
    try { return JSON.stringify(JSON.parse(t), null, 2); } catch { return t; }
  }

  function renderViolations(obj) {
    // поддержка обоих режимов: стандартного и human-json
    const viols = obj.violations || obj.violations_compact || [];
    if (!Array.isArray(viols) || viols.length === 0) return;

    $('#violBox').hidden = false;
    const ul = $('#violList');
    ul.innerHTML = '';
    for (const v of viols) {
      const li = document.createElement('li');
      const id = v.rule_id || v.id || '';
      const title = v.title || '';
      const sev = (v.severity || '').toString().toLowerCase();
      const ev = v.evidence || '';
      li.className = sev || '';
      li.innerHTML = `<div class="rid">${id} — ${title}</div>` +
        `<div class="sev">${sev || ''}</div>` +
        (ev ? `<div class="ev">${escapeHtml(ev)}</div>` : '');
      ul.appendChild(li);
    }
  }

  function renderDiagnostics(obj) {
    const meta = (obj.meta && obj.meta.llm) || null;
    const assessed = obj.assessed_rule_ids || [];
    if (!meta && (!assessed || assessed.length === 0)) return;
    $('#diagBox').hidden = false;
    const d = $('#diag');
    const s = [];
    if (meta) {
      s.push(`<div><b>mode</b>: ${escapeHtml(String(meta.mode || ''))}</div>`);
      s.push(`<div><b>model</b>: ${escapeHtml(String(meta.model || ''))}</div>`);
      if (meta.supports) s.push(`<div><b>supports</b>: ${escapeHtml(JSON.stringify(meta.supports))}</div>`);
      if (meta.duration_ms != null) s.push(`<div><b>duration</b>: ${Number(meta.duration_ms)} ms</div>`);
      if (meta.chunks != null) s.push(`<div><b>chunks</b>: ${Number(meta.chunks)}</div>`);
      if (meta.parse_errors) s.push(`<div><b>parse_errors</b>: ${Number(meta.parse_errors)}</div>`);
      if (meta.assessed_empty_chunks) s.push(`<div><b>assessed_empty_chunks</b>: ${Number(meta.assessed_empty_chunks)}</div>`);
      if (meta.assessed_weak_chunks) s.push(`<div><b>assessed_weak_chunks</b>: ${Number(meta.assessed_weak_chunks)}</div>`);
    }
    d.innerHTML = s.join('');

    const a = $('#assessed');
    if (Array.isArray(assessed) && assessed.length) {
      a.innerHTML = `<div><b>Оценённые правила</b> (${assessed.length}):</div>` +
        `<pre class="code">${escapeHtml(assessed.join('\n'))}</pre>`;
    }
  }

  function enableDownloads(obj, textMd) {
    const dlJson = $('#dlJson');
    const dlMd = $('#dlMd');
    dlJson.disabled = true; dlMd.disabled = true;
    if (obj) {
      dlJson.disabled = false;
      dlJson.onclick = () => downloadBlob(JSON.stringify(obj, null, 2), 'audit.json', 'application/json');
      // сгенерируем markdown из pretty_text если есть
      const md = (obj.pretty_text && typeof obj.pretty_text === 'string') ? obj.pretty_text : null;
      if (md) {
        dlMd.disabled = false;
        dlMd.onclick = () => downloadBlob(md, 'audit.md', 'text/markdown');
      }
    } else if (textMd) {
      dlMd.disabled = false;
      dlMd.onclick = () => downloadBlob(textMd, 'audit.md', 'text/markdown');
    }
  }

  function downloadBlob(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 0);
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
  }

  $('#run').addEventListener('click', audit);
})();
