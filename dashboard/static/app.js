// Vitriz Dashboard - frontend logic
const state = {
  sites: [],
  themes: [],
  currentSlug: null,
  currentData: null,
  pendingPatch: null,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function setStatus(msg, isError = false) {
  const s = $('#status');
  s.textContent = msg;
  s.className = isError ? 'text-red-600' : 'text-ink-600';
  if (!isError && msg !== 'Pret') setTimeout(() => { s.textContent = 'Pret'; }, 2500);
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) {
    const txt = await r.text();
    throw new Error(`${r.status} : ${txt}`);
  }
  return r.json();
}

// --- LIST OF SITES ---
async function loadSites() {
  state.sites = await api('/api/sites');
  state.themes = await api('/api/themes');
  renderSitesList();
  renderThemesGrid();
  fillImportThemes();
  if (state.sites.length) selectSite(state.sites[0].slug);
}

function renderSitesList() {
  const list = $('#sites-list');
  list.innerHTML = '';
  for (const s of state.sites) {
    const el = document.createElement('div');
    el.className = 'site-item' + (s.slug === state.currentSlug ? ' active' : '');
    el.innerHTML = `<span class="site-name">${s.name}</span><span class="site-meta">${s.city || s.theme}</span>`;
    el.onclick = () => selectSite(s.slug);
    list.appendChild(el);
  }
}

// --- LOAD A SITE ---
async function selectSite(slug) {
  state.currentSlug = slug;
  state.currentData = await api(`/api/sites/${slug}`);
  renderSitesList();
  renderEditForm();
  renderRawJson();
  highlightActiveTheme();
  reloadPreview();
}

function reloadPreview() {
  const ifr = $('#preview');
  const url = `/preview/${state.currentSlug}/?t=${Date.now()}`;
  ifr.src = url;
  $('#preview-url').textContent = `localhost:8000/preview/${state.currentSlug}/`;
}

// --- TAB SWITCH ---
$$('.tab-btn').forEach(btn => {
  btn.onclick = () => {
    const tab = btn.dataset.tab;
    $$('.tab-btn').forEach(b => {
      b.classList.toggle('border-accent', b === btn);
      b.classList.toggle('border-transparent', b !== btn);
      b.classList.toggle('text-ink-900', b === btn);
      b.classList.toggle('text-ink-600', b !== btn);
      b.classList.toggle('font-medium', b === btn);
    });
    $$('.tab-panel').forEach(p => p.classList.toggle('hidden', p.dataset.panel !== tab));
  };
});

// --- VIEWPORT ---
$$('.vp-btn').forEach(btn => {
  btn.onclick = () => {
    const v = btn.dataset.viewport;
    const wrap = $('#preview-wrap');
    if (v === 'mobile') wrap.style.width = '390px';
    else if (v === 'tablet') wrap.style.width = '820px';
    else wrap.style.width = '100%';
    $$('.vp-btn').forEach(b => {
      b.classList.toggle('bg-ink-900', b === btn);
      b.classList.toggle('text-white', b === btn);
      b.classList.toggle('border-ink-900', b === btn);
      b.classList.toggle('border-paper-300', b !== btn);
    });
  };
});

// --- EDIT FORM (dynamique) ---
function renderEditForm() {
  const root = $('#edit-form');
  root.innerHTML = '';
  const d = state.currentData;
  if (!d) return;

  root.appendChild(sectionCard('Marque', [
    field('brand.name', 'Nom affiche', d.brand?.name),
    field('brand.title', 'Title (onglet navigateur)', d.brand?.title),
    field('brand.meta_description', 'Meta description (SEO)', d.brand?.meta_description, 'textarea'),
    field('brand.footer_description', 'Description footer', d.brand?.footer_description, 'textarea'),
  ]));

  root.appendChild(sectionCard('Hero (haut de page)', [
    field('hero.eyebrow_text', 'Surtitre (ville/lieu)', d.hero?.eyebrow_text),
    field('hero.h1_html', 'Titre H1 (HTML : <br>, <em>)', d.hero?.h1_html, 'textarea'),
    field('hero.tagline', 'Tagline', d.hero?.tagline, 'textarea'),
  ]));

  root.appendChild(sectionCard('A propos', [
    field('about.h2_html', 'Titre H2', d.about?.h2_html, 'textarea'),
    field('about.signature', 'Signature (sous le titre)', d.about?.signature, 'textarea'),
  ]));

  // Paragraphes about (liste editable)
  if (Array.isArray(d.about?.paragraphs)) {
    const card = document.createElement('div');
    card.className = 'section-card';
    card.innerHTML = '<h3>Paragraphes "A propos"</h3>';
    d.about.paragraphs.forEach((p, i) => {
      card.appendChild(field(`about.paragraphs.${i}`, `Paragraphe ${i + 1}`, p, 'textarea'));
    });
    root.appendChild(card);
  }

  root.appendChild(sectionCard('Services / Soins', [
    field('services.h2_html', 'Titre H2', d.services?.h2_html, 'textarea'),
    field('services.intro', 'Introduction', d.services?.intro, 'textarea'),
  ]));

  // FAQ items
  if (d.faq?.items) {
    const card = document.createElement('div');
    card.className = 'section-card';
    card.innerHTML = `<h3>FAQ (${d.faq.items.length})</h3>`;
    d.faq.items.forEach((it, i) => {
      const wrap = document.createElement('div');
      wrap.className = 'space-y-2 pb-4 border-b border-paper-300 last:border-0';
      wrap.appendChild(field(`faq.items.${i}.q`, `Question ${i + 1}`, it.q));
      wrap.appendChild(field(`faq.items.${i}.a`, `Reponse ${i + 1}`, it.a, 'textarea'));
      card.appendChild(wrap);
    });
    root.appendChild(card);
  }

  root.appendChild(sectionCard('Contact', [
    field('contact.h2_html', 'Titre H2', d.contact?.h2_html, 'textarea'),
    field('contact.intro', 'Introduction', d.contact?.intro, 'textarea'),
  ]));
}

function sectionCard(title, fields) {
  const div = document.createElement('div');
  div.className = 'section-card';
  div.innerHTML = `<h3>${title}</h3>`;
  fields.forEach(f => div.appendChild(f));
  return div;
}

function field(path, label, value, type = 'text') {
  const wrap = document.createElement('div');
  wrap.className = 'field mb-3';
  const lbl = document.createElement('label');
  lbl.textContent = label;
  wrap.appendChild(lbl);
  let inp;
  if (type === 'textarea') {
    inp = document.createElement('textarea');
    inp.rows = Math.max(2, Math.min(6, (value || '').split('\n').length + 1));
  } else {
    inp = document.createElement('input');
    inp.type = 'text';
  }
  inp.value = value ?? '';
  inp.dataset.path = path;
  inp.oninput = () => setNested(state.currentData, path, inp.value);
  wrap.appendChild(inp);
  return wrap;
}

function setNested(obj, path, value) {
  const parts = path.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i];
    const isIdx = /^\d+$/.test(parts[i + 1]);
    if (cur[p] === undefined || cur[p] === null) cur[p] = isIdx ? [] : {};
    cur = cur[p];
  }
  cur[parts.at(-1)] = value;
}

// --- THEMES GRID ---
function renderThemesGrid() {
  const grid = $('#themes-grid');
  grid.innerHTML = '';
  for (const t of state.themes) {
    const el = document.createElement('div');
    el.className = 'theme-card';
    el.dataset.theme = t.name;
    el.innerHTML = `
      <div class="swatch">
        <span style="background: ${t.accent}"></span>
        <span style="background: ${t.paper}"></span>
        <span style="background: ${t.ink}"></span>
      </div>
      <div class="name">${t.name}</div>
      <div class="desc">${t.profession || ''} — ${t.display_font}</div>
    `;
    el.onclick = () => applyTheme(t.name);
    grid.appendChild(el);
  }
  highlightActiveTheme();
}

function highlightActiveTheme() {
  $$('.theme-card').forEach(c => c.classList.toggle('active', c.dataset.theme === state.currentData?.theme));
}

function applyTheme(name) {
  if (!state.currentData) return;
  state.currentData.theme = name;
  highlightActiveTheme();
  setStatus(`Theme : ${name} (clique Sauver puis Regenerer)`);
}

// --- RAW JSON ---
function renderRawJson() {
  $('#raw-json').value = JSON.stringify(state.currentData, null, 2);
}
$('#raw-json').oninput = (e) => {
  try {
    state.currentData = JSON.parse(e.target.value);
    setStatus('JSON valide');
  } catch (err) {
    setStatus('JSON invalide', true);
  }
};

// --- SAVE / REGENERATE ---
$('#btn-save').onclick = async () => {
  if (!state.currentSlug) return;
  setStatus('Sauvegarde...');
  await api(`/api/sites/${state.currentSlug}`, {
    method: 'PUT',
    body: JSON.stringify({ data: state.currentData }),
  });
  setStatus('Sauvegarde OK');
};

$('#btn-regenerate').onclick = async () => {
  if (!state.currentSlug) return;
  setStatus('Regeneration...');
  try {
    await api(`/api/sites/${state.currentSlug}/regenerate`, { method: 'POST' });
    reloadPreview();
    setStatus('Regeneration OK');
  } catch (e) {
    setStatus('Erreur : ' + e.message, true);
  }
};

$('#btn-deploy').onclick = async () => {
  if (!state.currentSlug) return;
  if (!confirm(`Déployer "${state.currentSlug}" sur Netlify ?`)) return;
  setStatus('Déploiement Netlify...');
  try {
    const resp = await api(`/api/sites/${state.currentSlug}/deploy`, { method: 'POST' });
    setStatus('Déployé : ' + resp.url);
    addChatMsg('system', `✓ Déployé sur Netlify : ${resp.url}`);
    window.open(resp.url, '_blank');
  } catch (e) {
    setStatus('Erreur deploy : ' + e.message, true);
    addChatMsg('system', 'Erreur déploiement : ' + e.message);
  }
};

// --- IMPORT PLANITY ---
function fillImportThemes() {
  const sel = $('#import-theme');
  if (!sel) return;
  sel.innerHTML = '';
  for (const t of state.themes) {
    const opt = document.createElement('option');
    opt.value = t.name;
    opt.textContent = `${t.name} — ${t.profession}`;
    sel.appendChild(opt);
  }
}

const importForm = $('#import-form');
if (importForm) {
  importForm.onsubmit = async (e) => {
    e.preventDefault();
    const url = $('#import-url').value.trim();
    const theme = $('#import-theme').value;
    const status = $('#import-status');
    status.classList.remove('hidden');
    status.textContent = 'Scraping en cours (10-30 sec)...';
    status.className = 'text-xs text-ink-600 mt-1';
    try {
      const resp = await api('/api/import/planity', {
        method: 'POST',
        body: JSON.stringify({ url, theme }),
      });
      status.textContent = `✓ ${resp.name} importé (${resp.n_services} services, ${resp.n_families} familles)`;
      status.className = 'text-xs text-green-700 mt-1';
      $('#import-url').value = '';
      // Refresh sites list and switch to it
      state.sites = await api('/api/sites');
      renderSitesList();
      selectSite(resp.slug);
    } catch (e) {
      status.textContent = '✗ ' + e.message;
      status.className = 'text-xs text-red-600 mt-1';
    }
  };
}

// --- SEARCH SITES ---
const searchInput = $('#sites-search');
if (searchInput) {
  searchInput.oninput = (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll('#sites-list .site-item').forEach(el => {
      const name = el.querySelector('.site-name')?.textContent.toLowerCase() || '';
      const meta = el.querySelector('.site-meta')?.textContent.toLowerCase() || '';
      el.style.display = (name.includes(q) || meta.includes(q)) ? '' : 'none';
    });
  };
}

// --- PROSPECTION (Lead Finder) ---
async function loadLeadOptions() {
  try {
    const [metiers, villes] = await Promise.all([
      api('/api/leads/metiers'),
      api('/api/leads/villes'),
    ]);
    const sel = $('#search-metier');
    if (sel) {
      sel.innerHTML = '<option value="">— Choisir —</option>';
      for (const m of metiers.metiers) {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        sel.appendChild(opt);
      }
    }
    const dl = $('#villes-list');
    if (dl) {
      dl.innerHTML = '';
      for (const v of villes.villes) {
        const opt = document.createElement('option');
        opt.value = v;
        dl.appendChild(opt);
      }
    }
  } catch (e) {
    console.warn('loadLeadOptions failed:', e);
  }
}

const searchForm = $('#search-form');
if (searchForm) {
  searchForm.onsubmit = async (e) => {
    e.preventDefault();
    const city = $('#search-city').value.trim();
    const metier = $('#search-metier').value;
    const limit = parseInt($('#search-limit').value, 10) || 20;
    const onlyNoSite = $('#search-only-no-site').checked;
    const status = $('#search-status');
    const results = $('#leads-results');
    if (!city || !metier) {
      status.textContent = 'Renseigne ville et métier';
      return;
    }
    status.textContent = '🔍 Recherche en cours...';
    results.innerHTML = '<div class="text-center py-8 text-ink-600 text-sm">Interrogation OpenStreetMap, patience 5-15 sec...</div>';
    try {
      const params = new URLSearchParams({
        city, metier, limit: String(limit),
        only_opportunities: onlyNoSite ? 'true' : 'false',
      });
      const resp = await api('/api/leads/search?' + params);
      if (resp.error) {
        status.textContent = '';
        results.innerHTML = `<div class="section-card text-sm text-red-600">${resp.error}<br><br>Métiers dispo : ${(resp.available || []).join(', ')}</div>`;
        return;
      }
      status.textContent = `✓ ${resp.leads.length} prospect(s) trouvé(s) (sur ${resp.total} au total)`;
      renderLeads(resp.leads);
    } catch (err) {
      status.textContent = '✗ ' + err.message;
      results.innerHTML = '';
    }
  };
}

function renderLeads(leads) {
  const root = $('#leads-results');
  if (!leads.length) {
    root.innerHTML = '<div class="section-card text-sm text-ink-600">Aucun prospect trouvé. Essaie une autre ville/métier ou décoche le filtre.</div>';
    return;
  }
  root.innerHTML = '';
  for (const lead of leads) {
    const card = document.createElement('div');
    card.className = 'section-card';
    const platforms = (lead.platforms || []).map(p => {
      const cls = p.is_real_site ? 'bg-red-100 text-red-700' : (p.type === 'booking' ? 'bg-blue-100 text-blue-700' : 'bg-pink-100 text-pink-700');
      return `<a href="${p.url}" target="_blank" class="inline-block px-2 py-0.5 text-xs rounded-full ${cls}">${p.icon} ${p.name}</a>`;
    }).join(' ');
    const hasSiteBadge = lead.has_real_site
      ? '<span class="inline-block px-2 py-0.5 text-xs rounded-full bg-red-100 text-red-700">⚠ Vrai site existant</span>'
      : '<span class="inline-block px-2 py-0.5 text-xs rounded-full bg-green-100 text-green-700">✓ Pas de vrai site</span>';
    const scoreColor = lead.score >= 70 ? 'text-green-700' : lead.score >= 40 ? 'text-orange-600' : 'text-ink-600';
    card.innerHTML = `
      <div class="flex items-start justify-between gap-4">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <h3 class="text-xl" style="margin: 0;">${escapeHtml(lead.nom)}</h3>
            <span class="${scoreColor} text-sm font-medium">${lead.score}/100</span>
          </div>
          <div class="text-sm text-ink-600 mb-2">
            ${escapeHtml(lead.adresse || lead.ville)}
            ${lead.telephone ? ' · ' + escapeHtml(lead.telephone) : ''}
          </div>
          <div class="flex flex-wrap items-center gap-2">
            ${hasSiteBadge}
            ${platforms}
            ${lead.lien_maps ? `<a href="${lead.lien_maps}" target="_blank" class="text-xs text-ink-600 underline">📍 Maps</a>` : ''}
          </div>
        </div>
        <div class="flex flex-col gap-2">
          <select class="lead-theme-select text-xs px-2 py-1 border border-paper-300 rounded">
            ${state.themes.map(t => `<option value="${t.name}">${t.name}</option>`).join('')}
          </select>
          <button class="lead-generate-btn px-3 py-1.5 bg-accent text-white text-xs rounded-full hover:bg-accent-600 transition" data-lead='${escapeAttr(JSON.stringify(lead))}'>
            ${lead.planity_url ? '⚡ Générer (Planity)' : 'Générer (squelette)'}
          </button>
        </div>
      </div>
    `;
    root.appendChild(card);
    const btn = card.querySelector('.lead-generate-btn');
    const sel = card.querySelector('.lead-theme-select');
    btn.onclick = () => generateFromLead(lead, sel.value, btn);
  }
}

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}
function escapeAttr(s) {
  return s.replace(/'/g, '&#39;');
}

async function generateFromLead(lead, theme, btn) {
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = '⏳ Génération...';
  try {
    const payload = {
      nom: lead.nom,
      metier: lead.metier,
      ville: lead.ville,
      adresse: lead.adresse || '',
      telephone: lead.telephone || '',
      website: lead.website || '',
      planity_url: lead.planity_url || '',
      instagram: (lead.platforms.find(p => p.name === 'Instagram') || {}).url || '',
      theme: theme || 'esthetique-rose',
    };
    const resp = await api('/api/leads/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    btn.textContent = '✓ Généré';
    btn.classList.add('bg-green-700');
    // Refresh sites list and switch
    state.sites = await api('/api/sites');
    renderSitesList();
    selectSite(resp.slug);
    // Switch to preview tab
    document.querySelector('.tab-btn[data-tab="preview"]')?.click();
  } catch (err) {
    btn.textContent = '✗ Erreur';
    btn.title = err.message;
    btn.disabled = false;
    setTimeout(() => { btn.textContent = originalText; }, 3000);
  }
}

// Init lead options on page load
loadLeadOptions();

// --- CHAT IA ---
const chatLog = $('#chat-log');

function addChatMsg(role, content, extra) {
  const el = document.createElement('div');
  el.className = `chat-msg ${role}`;
  if (typeof content === 'string') {
    el.textContent = content;
  } else {
    el.appendChild(content);
  }
  if (extra) el.appendChild(extra);
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
  return el;
}

$('#chat-form').onsubmit = async (e) => {
  e.preventDefault();
  const input = $('#chat-input');
  const msg = input.value.trim();
  if (!msg || !state.currentSlug) return;
  addChatMsg('user', msg);
  input.value = '';
  const thinking = addChatMsg('ai', 'Reflexion...');

  const autoApply = $('#auto-apply').checked;

  try {
    const resp = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ slug: state.currentSlug, message: msg, apply: autoApply }),
    });
    thinking.remove();
    addChatMsg('ai', resp.explanation || '(pas d\'explication)');
    if (resp.patch) {
      const pre = document.createElement('pre');
      pre.className = 'patch-preview';
      pre.textContent = JSON.stringify(resp.patch, null, 2);
      const wrapper = document.createElement('div');
      wrapper.appendChild(pre);
      if (!resp.applied) {
        const btn = document.createElement('button');
        btn.textContent = 'Appliquer';
        btn.className = 'primary';
        btn.onclick = async () => {
          await api(`/api/sites/${state.currentSlug}/apply_patch`, {
            method: 'POST',
            body: JSON.stringify({ patch: resp.patch }),
          });
          state.currentData = await api(`/api/sites/${state.currentSlug}`);
          renderEditForm();
          renderRawJson();
          highlightActiveTheme();
          reloadPreview();
          btn.disabled = true;
          btn.textContent = 'Applique';
          setStatus('Modification appliquee');
        };
        wrapper.appendChild(btn);
      } else {
        const tag = document.createElement('div');
        tag.className = 'text-xs text-green-700 mt-1';
        tag.textContent = '✓ Modification appliquee automatiquement';
        wrapper.appendChild(tag);
        // Refresh
        state.currentData = await api(`/api/sites/${state.currentSlug}`);
        renderEditForm();
        renderRawJson();
        highlightActiveTheme();
        reloadPreview();
      }
      chatLog.lastChild.appendChild(wrapper);
    }
  } catch (e) {
    thinking.remove();
    addChatMsg('system', 'Erreur : ' + e.message);
  }
};

// --- INIT ---
loadSites().catch(e => setStatus('Erreur init : ' + e.message, true));
