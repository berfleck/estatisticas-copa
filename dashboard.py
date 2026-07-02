#!/usr/bin/env python3
"""
dashboard.py
------------
Gera um dashboard HTML interativo e OFFLINE (dashboard.html) a partir dos
dados coletados de TODA a Copa. É um arquivo único, sem servidor e sem
dependências — basta abrir no navegador (duplo-clique).

Recursos:
    - Buscar/selecionar seleções (48+) e jogos específicos.
    - Filtrar por fase (Grupos, Oitavas, Quartas, ...).
    - Ver stats de um jogo, ou somadas/médias de um subconjunto.
    - Comparar seleções e jogos lado a lado, com barras por métrica.

Uso (chamado automaticamente por sofascore_stats.py):
    from dashboard import build_dashboard
    build_dashboard(games, groups, "dashboard.html", phases=[...])
"""

import json


def build_dashboard(games, groups, out_path="dashboard.html",
                    phases=None, generated_at=""):
    """
    games : lista de dicts {selecao, adversario, placar, fase, event_id,
                            values:{rótulo: valor}}
    groups: lista de dicts {name, stats:[rótulo, ...]}
    phases: lista ordenada de fases presentes (para os chips).
    """
    payload = {
        "games": games,
        "groups": groups,
        "phases": phases or [],
        "generatedAt": generated_at,
    }
    data_json = json.dumps(payload, ensure_ascii=False)
    html = _TEMPLATE.replace("__DATA__", data_json)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


_TEMPLATE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estatísticas — Copa do Mundo 2026</title>
<style>
  :root{
    --page:#f9f9f7; --surface:#fcfcfb; --border:rgba(11,11,11,.10);
    --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
    --grid:#e1e0d9; --baseline:#c3c2b7; --track:#eeece6;
    --s1:#e34948; --s2:#2a78d6; --s3:#1baf7a; --s4:#eb6834;
    --s5:#4a3aa7; --s6:#e87ba4; --s7:#eda100; --s8:#008300;
    --accent:#2a78d6;
  }
  @media (prefers-color-scheme: dark){
    :root{
      --page:#0d0d0d; --surface:#1a1a19; --border:rgba(255,255,255,.10);
      --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
      --grid:#2c2c2a; --baseline:#383835; --track:#26261f;
      --s1:#e66767; --s2:#3987e5; --s3:#199e70; --s4:#d95926;
      --s5:#9085e9; --s6:#d55181; --s7:#c98500; --s8:#008300;
      --accent:#3987e5;
    }
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{
    background:var(--page); color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
    font-size:14px; line-height:1.4; padding:24px;
    -webkit-font-smoothing:antialiased;
  }
  .wrap{max-width:1320px; margin:0 auto}
  header.top{margin-bottom:14px}
  h1{font-size:22px; margin:0 0 4px; letter-spacing:-.01em}
  .sub{color:var(--ink2); font-size:13px}
  .meta{color:var(--muted); font-size:12px; margin-top:6px}

  .toolbar{
    display:flex; flex-wrap:wrap; gap:10px 16px; align-items:center;
    padding:12px 0; border-top:1px solid var(--grid);
    border-bottom:1px solid var(--grid); margin:12px 0 0;
  }
  .seg{display:inline-flex; background:var(--track); border-radius:9px; padding:3px}
  .seg button{
    border:0; background:transparent; color:var(--ink2); cursor:pointer;
    font:inherit; font-size:13px; padding:6px 12px; border-radius:7px;
  }
  .seg button.on{background:var(--surface); color:var(--ink);
    box-shadow:0 1px 2px rgba(0,0,0,.12); font-weight:600}
  .tlabel{font-size:12px; color:var(--muted); margin-right:2px}
  .grow{flex:1}
  input.search{
    font:inherit; font-size:13px; padding:7px 10px;
    border:1px solid var(--border); border-radius:8px;
    background:var(--surface); color:var(--ink);
  }
  input.metric{min-width:160px}
  .chiprow{display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-top:10px}
  .chiprow .tlabel{margin-right:4px}
  .chip{
    border:1px solid var(--border); background:var(--surface); color:var(--ink2);
    border-radius:999px; padding:5px 11px; font-size:12px; cursor:pointer;
    user-select:none;
  }
  .chip.on{background:var(--ink); color:var(--surface); border-color:var(--ink)}

  .layout{display:grid; grid-template-columns:260px 1fr; gap:20px; margin-top:16px}
  @media (max-width:800px){ .layout{grid-template-columns:1fr} }

  aside .card, main .card{
    background:var(--surface); border:1px solid var(--border);
    border-radius:12px; padding:14px;
  }
  aside h3{font-size:12px; text-transform:uppercase; letter-spacing:.05em;
    color:var(--muted); margin:0 0 8px; display:flex; justify-content:space-between}
  .qbtns{display:flex; gap:6px; flex-wrap:wrap; margin:8px 0 10px}
  .qbtn{border:1px solid var(--border); background:transparent; color:var(--ink2);
    border-radius:7px; padding:5px 8px; font:inherit; font-size:12px; cursor:pointer}
  .qbtn:hover{border-color:var(--muted)}
  input.teamfilter{width:100%; margin-bottom:8px}
  .teamlist{max-height:66vh; overflow:auto; margin:0 -4px; padding:0 4px}
  .listdivider{font-size:10px; text-transform:uppercase; letter-spacing:.05em;
    color:var(--muted); padding:11px 2px 5px; margin-top:4px;
    border-top:1px dashed var(--grid)}
  .teamblock{border-bottom:1px solid var(--grid)}
  .teamhead{display:flex; align-items:center; gap:8px; padding:7px 2px;
    font-size:13px; cursor:pointer}
  .teamhead .nm{font-weight:600; flex:1}
  .teamhead .ct{color:var(--muted); font-size:11px; font-variant-numeric:tabular-nums}
  .caret{color:var(--muted); font-size:10px; width:10px; transition:transform .12s}
  .caret.open{transform:rotate(90deg)}
  .dot{width:10px; height:10px; border-radius:3px; flex:0 0 auto}
  .games{padding:2px 0 8px 26px}
  .gopt{display:flex; align-items:center; gap:8px; padding:3px 0; font-size:13px;
    color:var(--ink2); cursor:pointer}
  .gopt .pl{margin-left:auto; color:var(--muted); font-variant-numeric:tabular-nums; font-size:12px}
  .gopt .fs{color:var(--muted); font-size:11px}
  input[type=checkbox]{accent-color:var(--accent); width:15px; height:15px; flex:0 0 auto}

  .legend{display:flex; gap:12px; flex-wrap:wrap; margin:0 0 12px; font-size:12px; color:var(--ink2)}
  .legend .it{display:inline-flex; align-items:center; gap:6px}

  .scroll{overflow-x:auto}
  table{border-collapse:collapse; width:100%; font-size:13px}
  thead th{position:sticky; top:0; background:var(--surface); z-index:2}
  th.stat, td.stat{
    text-align:left; position:sticky; left:0; background:var(--surface); z-index:1;
    min-width:180px; font-weight:500; color:var(--ink2); border-right:1px solid var(--grid);
  }
  thead th.stat{z-index:3}
  th.col{padding:8px 10px; text-align:right; vertical-align:bottom; min-width:106px}
  .colhead{display:flex; flex-direction:column; align-items:flex-end; gap:2px}
  .colhead .nm{display:flex; align-items:center; gap:6px; font-weight:600}
  .colhead .pl{font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums}
  .colhead .fs{font-size:10px; color:var(--muted)}
  .colhead .bar-under{height:3px; width:100%; border-radius:2px; margin-top:3px}
  tr.grouprow td{padding:12px 10px 5px; font-size:11px; text-transform:uppercase;
    letter-spacing:.05em; color:var(--muted); font-weight:600; border-bottom:1px solid var(--grid)}
  tbody td.val{padding:6px 10px; vertical-align:middle}
  tbody tr.statrow:hover td{background:color-mix(in srgb, var(--accent) 7%, transparent)}
  tbody tr.statrow:hover td.stat{background:color-mix(in srgb, var(--accent) 9%, var(--surface))}
  .cell{display:flex; flex-direction:column; align-items:flex-end; gap:3px}
  .num{font-variant-numeric:tabular-nums; letter-spacing:-.01em}
  .num.lead{font-weight:700}
  .track{width:100%; height:5px; background:var(--track); border-radius:3px; overflow:hidden}
  .fill{height:100%; border-radius:3px; min-width:2px}
  .empty{padding:44px 10px; text-align:center; color:var(--muted)}
  .foot{margin-top:16px; color:var(--muted); font-size:12px}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <h1>Estatísticas — Copa do Mundo 2026</h1>
    <div class="sub">Todas as seleções e jogos, via Sofascore. Busque, filtre por fase, some/médie e compare.</div>
    <div class="meta" id="meta"></div>
  </header>

  <div class="toolbar">
    <span class="tlabel">Ver</span>
    <div class="seg" id="viewseg">
      <button data-view="jogo" class="on">Por jogo</button>
      <button data-view="selecao">Por seleção</button>
    </div>
    <span class="tlabel" id="agglabel">Agregar</span>
    <div class="seg" id="aggseg">
      <button data-agg="soma" class="on">Soma</button>
      <button data-agg="media">Média/jogo</button>
    </div>
    <span class="grow"></span>
    <input class="search metric" id="search" placeholder="filtrar métrica…" autocomplete="off">
  </div>
  <div class="chiprow" id="phaserow"><span class="tlabel">Fase</span></div>
  <div class="chiprow" id="grouprow"><span class="tlabel">Métricas</span></div>

  <div class="layout">
    <aside>
      <div class="card">
        <h3><span>Seleções &amp; jogos</span><span id="selcount"></span></h3>
        <input class="search teamfilter" id="teamfilter" placeholder="buscar seleção…" autocomplete="off">
        <div class="qbtns" id="qbtns"></div>
        <div class="teamlist" id="teamlist"></div>
      </div>
    </aside>
    <main>
      <div class="card">
        <div class="legend" id="legend"></div>
        <div class="scroll"><table id="tbl"></table></div>
        <div class="empty" id="empty" style="display:none">Selecione ao menos um jogo à esquerda.</div>
      </div>
    </main>
  </div>

  <div class="foot" id="foot"></div>
</div>

<script id="viz-data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('viz-data').textContent);
const GAMES = DATA.games;
GAMES.forEach((g, i) => g._id = i);          // id único por (seleção x jogo)
const GROUPS = DATA.groups;
const PHASES = DATA.phases;

// seleções em ordem alfabética (pt-BR, respeitando acentos)
const TEAMS = [...new Set(GAMES.map(g => g.selecao))]
  .sort((a, b) => a.localeCompare(b, 'pt-BR'));

// Abre em TELA LIMPA: nada selecionado, todas as fases/métricas ativas.
const state = {
  selected: new Set(),
  phases: new Set(PHASES),
  groups: new Set(GROUPS.map(g => g.name)),
  expanded: new Set(),
  view: 'jogo',
  agg: 'soma',
  query: '',
  teamQuery: '',
};

// fase mais recente com jogos (última na ordem canônica) — atalho "Fase atual"
const LATEST_PHASE = PHASES.length ? PHASES[PHASES.length - 1] : null;

const isPct = l => l.includes('(%)');
const round2 = x => Math.round(x * 100) / 100;
function fmt(v){
  if (v === null || v === undefined) return '–';
  return Number.isInteger(v) ? v.toLocaleString('pt-BR')
    : v.toLocaleString('pt-BR', {maximumFractionDigits: 2});
}

// jogos elegíveis = selecionados E cuja fase está ativa
const activeGames = () => GAMES.filter(g => state.selected.has(g._id) && state.phases.has(g.fase));
// jogos de um time visíveis pela fase (para a lista)
const teamGames = t => GAMES.filter(g => g.selecao === t && state.phases.has(g.fase));
// seleções com ao menos 1 jogo ativo, em ordem global
function activeTeams(){
  const set = new Set(activeGames().map(g => g.selecao));
  return TEAMS.filter(t => set.has(t));
}
// cor segue a seleção; atribuída na ordem das seleções ativas (subconjunto sempre distinto)
function teamColor(t){
  const i = activeTeams().indexOf(t);
  return i >= 0 ? `var(--s${(i % 8) + 1})` : 'var(--muted)';
}

function activeStats(){
  const q = state.query.trim().toLowerCase();
  const out = [];
  GROUPS.forEach(gr => {
    if (!state.groups.has(gr.name)) return;
    gr.stats.forEach(lbl => {
      if (q && !lbl.toLowerCase().includes(q)) return;
      out.push({group: gr.name, label: lbl});
    });
  });
  return out;
}

function aggregate(games, label){
  const vals = games.map(g => g.values[label]).filter(v => v !== null && v !== undefined);
  if (!vals.length) return null;
  const sum = vals.reduce((a, b) => a + b, 0);
  if (isPct(label) || state.agg === 'media') return round2(sum / vals.length);
  return round2(sum);
}

function columns(){
  const games = activeGames();
  if (state.view === 'jogo'){
    // ordena por ordem das seleções ativas, mantendo ordem cronológica dentro
    const order = activeTeams();
    const sorted = games.slice().sort((a, b) =>
      order.indexOf(a.selecao) - order.indexOf(b.selecao) || a._id - b._id);
    return sorted.map(g => ({
      team: g.selecao, title: 'vs ' + g.adversario, sub: g.placar, fase: g.fase,
      value: label => g.values[label],
    }));
  }
  return activeTeams().map(t => {
    const tg = games.filter(g => g.selecao === t);
    return {
      team: t, title: t, sub: tg.length + (tg.length === 1 ? ' jogo' : ' jogos'), fase: '',
      value: label => aggregate(tg, label),
    };
  });
}

function render(){
  renderMeta(); renderPhaseChips(); renderGroupChips();
  renderQuick(); renderTeamList();
  const showAgg = state.view === 'selecao';
  document.getElementById('agglabel').style.display =
    document.getElementById('aggseg').style.display = showAgg ? '' : 'none';
  renderTable(); renderFoot();
}

function renderMeta(){
  const g = activeGames();
  const teams = activeTeams().length;
  const gen = DATA.generatedAt ? ' — atualizado em ' + DATA.generatedAt : '';
  const totalGames = new Set(GAMES.map(x => x.event_id)).size;
  document.getElementById('meta').textContent =
    `Base: ${totalGames} jogos, ${TEAMS.length} seleções · Visão atual: ${g.length} jogo(s), ${teams} seleção(ões)${gen}`;
  document.getElementById('selcount').textContent = state.selected.size + ' sel.';
}

function chip(text, on, fn){
  const c = document.createElement('div');
  c.className = 'chip' + (on ? ' on' : '');
  c.textContent = text; c.onclick = fn; return c;
}

function renderPhaseChips(){
  const el = document.getElementById('phaserow');
  el.querySelectorAll('.chip').forEach(n => n.remove());
  el.appendChild(chip('Todas', state.phases.size === PHASES.length, () => {
    if (state.phases.size === PHASES.length) state.phases.clear();
    else state.phases = new Set(PHASES);
    render();
  }));
  PHASES.forEach(p => el.appendChild(chip(p, state.phases.has(p), () => {
    state.phases.has(p) ? state.phases.delete(p) : state.phases.add(p);
    render();
  })));
}

function renderGroupChips(){
  const el = document.getElementById('grouprow');
  el.querySelectorAll('.chip').forEach(n => n.remove());
  el.appendChild(chip('Todas', state.groups.size === GROUPS.length, () => {
    if (state.groups.size === GROUPS.length) state.groups.clear();
    else state.groups = new Set(GROUPS.map(g => g.name));
    render();
  }));
  GROUPS.forEach(gr => el.appendChild(chip(gr.name, state.groups.has(gr.name), () => {
    state.groups.has(gr.name) ? state.groups.delete(gr.name) : state.groups.add(gr.name);
    render();
  })));
}

function renderQuick(){
  const el = document.getElementById('qbtns');
  el.innerHTML = '';
  const mk = (txt, fn) => {
    const b = document.createElement('button');
    b.className = 'qbtn'; b.textContent = txt;
    b.onclick = () => { fn(); render(); };
    el.appendChild(b);
  };
  mk('Limpar seleção', () => state.selected.clear());
  if (LATEST_PHASE){
    mk('Fase atual (' + LATEST_PHASE + ')', () => {
      state.selected = new Set(GAMES.filter(g => g.fase === LATEST_PHASE).map(g => g._id));
    });
  }
}

function renderTeamList(){
  const el = document.getElementById('teamlist');
  el.innerHTML = '';
  const q = state.teamQuery.trim().toLowerCase();
  const isSel = t => teamGames(t).some(g => state.selected.has(g._id));

  // visíveis (com jogo na fase ativa + busca) e ordenadas:
  // selecionadas no topo, cada grupo em ordem alfabética.
  const visible = TEAMS
    .filter(t => teamGames(t).length && (!q || t.toLowerCase().includes(q)));
  const anySel = visible.some(isSel);
  const ordered = visible.slice().sort((a, b) =>
    (isSel(a) ? 0 : 1) - (isSel(b) ? 0 : 1) || a.localeCompare(b, 'pt-BR'));

  let dividerPut = false;
  ordered.forEach(t => {
    // divisor entre "selecionadas" e "demais seleções"
    if (anySel && !dividerPut && !isSel(t)){
      const d = document.createElement('div');
      d.className = 'listdivider';
      d.textContent = 'demais seleções';
      el.appendChild(d);
      dividerPut = true;
    }
    const tg = teamGames(t);
    const selCount = tg.filter(g => state.selected.has(g._id)).length;
    const allOn = selCount === tg.length;
    const block = document.createElement('div');
    block.className = 'teamblock';

    const head = document.createElement('div');
    head.className = 'teamhead';
    const open = state.expanded.has(t);
    head.innerHTML =
      `<span class="caret ${open ? 'open' : ''}">▶</span>` +
      `<span class="dot" style="background:${teamColor(t)}"></span>` +
      `<input type="checkbox" ${allOn ? 'checked' : ''}>` +
      `<span class="nm">${t}</span>` +
      `<span class="ct">${selCount}/${tg.length}</span>`;
    // clique no nome/caret expande; no checkbox seleciona
    head.querySelector('.nm').onclick = head.querySelector('.caret').onclick = () => {
      state.expanded.has(t) ? state.expanded.delete(t) : state.expanded.add(t);
      render();
    };
    head.querySelector('input').onchange = e => {
      tg.forEach(g => e.target.checked ? state.selected.add(g._id) : state.selected.delete(g._id));
      render();
    };
    block.appendChild(head);

    if (open){
      const box = document.createElement('div');
      box.className = 'games';
      tg.forEach(g => {
        const row = document.createElement('label');
        row.className = 'gopt';
        row.innerHTML =
          `<input type="checkbox" ${state.selected.has(g._id) ? 'checked' : ''}>` +
          `<span>vs ${g.adversario}</span><span class="fs">${g.fase}</span>` +
          `<span class="pl">${g.placar}</span>`;
        row.querySelector('input').onchange = e => {
          e.target.checked ? state.selected.add(g._id) : state.selected.delete(g._id);
          render();
        };
        box.appendChild(row);
      });
      block.appendChild(box);
    }
    el.appendChild(block);
  });
}

function renderTable(){
  const cols = columns();
  const stats = activeStats();
  const tbl = document.getElementById('tbl');
  const empty = document.getElementById('empty');
  const legend = document.getElementById('legend');

  if (!cols.length){ tbl.innerHTML = ''; legend.innerHTML = ''; empty.style.display = ''; return; }
  empty.style.display = 'none';

  const teamsShown = [...new Set(cols.map(c => c.team))];
  legend.innerHTML = teamsShown.map(t =>
    `<span class="it"><span class="dot" style="background:${teamColor(t)}"></span>${t}</span>`).join('');

  let head = '<thead><tr><th class="stat">Estatística</th>';
  cols.forEach(c => {
    head += `<th class="col"><div class="colhead">` +
      `<span class="nm"><span class="dot" style="background:${teamColor(c.team)}"></span>${c.title}</span>` +
      `<span class="pl">${c.sub}</span>` +
      (c.fase ? `<span class="fs">${c.fase}</span>` : '') +
      `<span class="bar-under" style="background:${teamColor(c.team)}"></span></div></th>`;
  });
  head += '</tr></thead>';

  let body = '<tbody>';
  let curGroup = null;
  stats.forEach(s => {
    if (s.group !== curGroup){
      curGroup = s.group;
      body += `<tr class="grouprow"><td colspan="${cols.length + 1}">${curGroup}</td></tr>`;
    }
    const raw = cols.map(c => c.value(s.label));
    const nums = raw.filter(v => v !== null && v !== undefined);
    const hasNeg = nums.some(v => v < 0);
    const max = nums.length ? Math.max(...nums) : 0;
    const lead = nums.length ? Math.max(...nums) : null;
    body += `<tr class="statrow"><td class="stat">${s.label}</td>`;
    cols.forEach((c, i) => {
      const v = raw[i];
      const isLead = v !== null && v !== undefined && cols.length > 1 && v === lead && max !== 0;
      let bar = '';
      if (!hasNeg && v !== null && v !== undefined && max > 0){
        const w = Math.max(2, Math.round((v / max) * 100));
        bar = `<div class="track"><div class="fill" style="width:${w}%;background:${teamColor(c.team)}"></div></div>`;
      }
      body += `<td class="val"><div class="cell"><span class="num${isLead ? ' lead' : ''}">${fmt(v)}</span>${bar}</div></td>`;
    });
    body += '</tr>';
  });
  body += '</tbody>';
  tbl.innerHTML = head + body;
}

function renderFoot(){
  document.getElementById('foot').textContent =
    'Percentuais são sempre média; contagens seguem Soma/Média. As barras comparam valores dentro de cada linha; ' +
    'em métricas com valor negativo (ex.: Gols Evitados) a barra é omitida. Cores são atribuídas às seleções em exibição.';
}

document.getElementById('viewseg').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  state.view = b.dataset.view;
  [...e.currentTarget.children].forEach(x => x.classList.toggle('on', x === b));
  render();
};
document.getElementById('aggseg').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  state.agg = b.dataset.agg;
  [...e.currentTarget.children].forEach(x => x.classList.toggle('on', x === b));
  render();
};
document.getElementById('search').oninput = e => { state.query = e.target.value; renderTable(); };
document.getElementById('teamfilter').oninput = e => { state.teamQuery = e.target.value; renderTeamList(); };

render();
</script>
</body>
</html>
"""
