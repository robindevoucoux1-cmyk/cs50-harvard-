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

$('#btn-deploy').onclick = () => {
  alert('Deploy Netlify : a implementer dans la prochaine etape. Pour l\'instant tu peux uploader le ZIP manuellement.');
};

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
