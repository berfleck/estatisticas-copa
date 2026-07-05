#!/usr/bin/env python3
"""
dashboard.py
------------
Gera um dashboard HTML interativo e OFFLINE (dashboard.html) a partir dos
dados coletados de TODA a Copa. É um arquivo único, sem servidor e sem
dependências — basta abrir no navegador (duplo-clique). As fontes (Google
Fonts) são progressivas: sem internet, cai nas fontes do sistema.

Três visões:
    - Painel  : ranking de todas as seleções por IFE/IDO (+ métrica à escolha).
    - Comparar: até 4 seleções lado a lado — radar das 5 dimensões compostas
                (Ataque, Finalização, Construção, Pressão, Defesa), projeção
                de confronto direto pela diferença de IFE e barras por métrica.
    - Perfil  : uma seleção em detalhe — índices, jogos (incluir/excluir um
                jogo recalcula IFE/IDO/dimensões) e ranking em cada métrica.

Uso (chamado automaticamente por sofascore_stats.py):
    from dashboard import build_dashboard
    build_dashboard(games, groups, "dashboard.html", phases=[...])
"""

import json

from flags import TEAM_FLAGS


def build_dashboard(games, groups, out_path="dashboard.html",
                    phases=None, generated_at="", descriptions=None,
                    ife_mkt=None, ife_shrink=4.0,
                    dims=None, dims_baseline=None):
    """
    games : lista de dicts {selecao, adversario, placar, fase, event_id,
                            ifeRes, values:{rótulo: valor}}
    groups: lista de dicts {name, stats:[rótulo, ...]}
    phases: lista ordenada de fases presentes (para os chips).
    descriptions: dict {rótulo: texto} — tooltip exibido ao passar o mouse
                  sobre o nome da métrica (só as que precisam de explicação).
    ife_mkt: dict {seleção: rating de mercado} — com o ifeRes de cada jogo,
             permite recalcular o IFE no navegador considerando só os jogos
             selecionados: mercado + média(resíduos) × n/(n+ife_shrink).
    dims: spec canônica das 5 dimensões compostas
          ({nome: [(métrica, peso[, inverter])]}). Se omitida/vazia, o
          dashboard usa a spec embutida no próprio HTML.
    dims_baseline: régua global {métrica: {mean, sd}} dos z-scores das
          dimensões. Se omitida/vazia, o dashboard monta a régua no cliente
          a partir dos próprios games.

    As bandeiras (TEAM_FLAGS) vão DENTRO do payload, na chave "flags" —
    o template lê DATA.flags.
    """
    payload = {
        "games": games,
        "groups": groups,
        "phases": phases or [],
        "descriptions": descriptions or {},
        "ifeMkt": ife_mkt or {},
        "ifeShrink": ife_shrink,
        # None (e não {}) quando ausentes: o front testa truthiness antes de
        # substituir a spec/régua locais.
        "dims": dims or None,
        "dimsBaseline": dims_baseline or None,
        "flags": TEAM_FLAGS,
        "generatedAt": generated_at,
    }
    # count=1: substitui SÓ o placeholder do <script id="viz-data"> (a 1ª
    # ocorrência); um eventual "__DATA__" em texto/JS do template fica intacto.
    html = _TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False), 1)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


_TEMPLATE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estatísticas — Copa do Mundo 2026</title>
<!-- favicon: bola de futebol em SVG inline (data URI) — offline, sem arquivo extra -->
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='29' fill='%23fbfaf6' stroke='%231a1813' stroke-width='4'/%3E%3Cg stroke='%231a1813' stroke-width='3' stroke-linecap='round'%3E%3Cline x1='32' y1='20' x2='32' y2='5'/%3E%3Cline x1='43.4' y1='28.3' x2='57.7' y2='23.7'/%3E%3Cline x1='39.1' y1='41.7' x2='47.9' y2='53.8'/%3E%3Cline x1='24.9' y1='41.7' x2='16.1' y2='53.8'/%3E%3Cline x1='20.6' y1='28.3' x2='6.3' y2='23.7'/%3E%3C/g%3E%3Cpolygon points='32,20 43.4,28.3 39.1,41.7 24.9,41.7 20.6,28.3' fill='%231a1813'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:ital,wght@0,400;0,500;0,600;0,700;0,800;1,500&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600&display=swap" rel="stylesheet">
<style>
:root{
  --page:#f0ede4; --surface:#fbfaf6; --ink:#1a1813; --ink2:#3d3a33;
  --muted:#8f8a7e; --faint:#a39d8e; --line:rgba(26,24,19,.09);
  --acc:#2f7d55; --red:#c0392b; --ora:#c8781c;
  --serif:'Newsreader',Georgia,serif; --sans:'Archivo',system-ui,-apple-system,'Segoe UI',sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--page);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.4;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
::selection{background:var(--acc);color:#fff}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:rgba(26,24,19,.18);border-radius:8px;border:3px solid var(--page)}
input:focus{outline:none}
button{font:inherit}
@keyframes shimmer{0%{opacity:.5}50%{opacity:1}100%{opacity:.5}}

.wrap{max-width:1160px;margin:0 auto;padding:0 24px 72px}
.head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:30px 0 20px}
.kicker{display:flex;align-items:center;gap:9px;color:var(--acc);font-weight:700;font-size:11px;letter-spacing:.14em;text-transform:uppercase}
.dot8{width:8px;height:8px;border-radius:50%;background:var(--acc)}
h1{font-family:var(--serif);font-weight:500;font-size:34px;line-height:1.02;letter-spacing:-.01em;margin:8px 0 0}
h1 .dim{color:var(--faint)}
.metaR{text-align:right;color:#6b665b;font-size:12.5px;font-variant-numeric:tabular-nums;line-height:1.6}
.metaR b{font-weight:600;color:var(--ink2)}

.toolbar{position:sticky;top:0;z-index:30;margin:0 -24px;padding:12px 24px;background:rgba(240,237,228,.9);backdrop-filter:blur(10px);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.tools{display:flex;align-items:center;gap:14px 18px;flex-wrap:wrap}
.seg{display:inline-flex;background:#e3dfd3;border-radius:11px;padding:3px;gap:2px}
.seg.sm{border-radius:10px}
.seg button{border:0;background:transparent;color:#6b665b;cursor:pointer;font-size:13px;font-weight:500;padding:6px 14px;border-radius:8px}
.seg button.on{background:var(--surface);color:var(--ink);box-shadow:0 1px 2px rgba(0,0,0,.14);font-weight:600}
.vr{width:1px;height:22px;background:rgba(26,24,19,.12)}
.tlabel{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.chips{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.chip{border:1px solid rgba(26,24,19,.12);background:var(--surface);color:#6b665b;border-radius:999px;padding:5px 11px;font-size:12px;cursor:pointer}
.chip.on{background:var(--ink);color:var(--page);border-color:var(--ink);font-weight:600}
.restore{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:600;color:var(--ora);background:rgba(200,120,28,.1);border:1px solid rgba(200,120,28,.3);border-radius:999px;padding:5px 11px;cursor:pointer}

section{padding-top:22px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px}
.explain{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:22px}
.exc{background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:14px 16px}
.exc.ife{border-left:3px solid var(--acc)} .exc.ido{border-left:3px solid var(--ora)}
.exc h4{margin:0;font-size:13px;font-weight:700;letter-spacing:.02em}
.exc p{margin:4px 0 0;color:#6b665b;font-size:12.5px;line-height:1.5}
.sechead{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:14px}
.overline{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600}
.title{font-family:var(--serif);font-size:26px;font-weight:500;letter-spacing:-.01em;margin-top:2px}
.title.lg{font-size:27px}
.rowctrl{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.custbtn{cursor:pointer;font-size:13px;font-weight:500;color:#6b665b;border:1px solid rgba(26,24,19,.16);border-radius:9px;padding:6px 12px;background:transparent}
.custbtn.on{color:var(--acc);background:rgba(47,125,85,.1);border-color:rgba(47,125,85,.35);font-weight:600}
.xbtn{cursor:pointer;color:var(--faint);font-size:15px;background:none;border:0}

.menu{position:absolute;top:100%;margin-top:8px;width:340px;max-width:82vw;background:#fff;border:1px solid rgba(26,24,19,.12);border-radius:14px;box-shadow:0 18px 46px -12px rgba(26,24,19,.3);z-index:40;overflow:hidden}
.menu .mh{padding:10px;border-bottom:1px solid var(--line)}
.menu input{width:100%;font-size:13px;padding:8px 11px;border:1px solid rgba(26,24,19,.14);border-radius:9px;background:#f7f5ef;color:var(--ink)}
.menu .ml{max-height:52vh;overflow:auto;padding:6px}
.mgrp{padding:9px 8px 4px;font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint);font-weight:700}
.mitem{display:block;width:100%;text-align:left;padding:8px 9px;border-radius:8px;font-size:13.5px;color:var(--ink2);background:none;border:0;cursor:pointer}
.mitem:hover{background:#f2efe7}
.mitem.on{font-weight:600;background:rgba(47,125,85,.12);color:var(--acc)}

.collbl{display:flex;align-items:center;gap:13px;padding:0 12px 7px;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);font-weight:700}
.board{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:6px}
.brow{display:flex;align-items:center;gap:13px;width:100%;padding:9px 12px;border-radius:11px;border:0;background:none;cursor:pointer;text-align:left}
.brow:hover{background:#f2efe7}
.rank{width:26px;text-align:center;font-variant-numeric:tabular-nums;font-weight:700;font-size:14px;color:var(--faint);flex:0 0 auto}
.flag{width:26px;height:18px;border-radius:3px;object-fit:cover;box-shadow:0 0 0 .5px rgba(26,24,19,.2);flex:0 0 auto}
.bname{display:flex;flex-direction:column;line-height:1.15;flex:1;min-width:0}
.bname .nm{font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bname .sub{font-size:11px;color:var(--faint)}
.ifetrack{position:relative;width:150px;height:16px;flex:0 0 auto}
.ifecenter{position:absolute;top:0;bottom:0;left:50%;width:1px;background:rgba(26,24,19,.22)}
.ifefill{position:absolute;top:3px;bottom:3px}
.ifeval{width:62px;text-align:right;font-variant-numeric:tabular-nums;font-weight:700;font-size:16px;letter-spacing:-.01em;flex:0 0 auto}
.idowrap{width:66px;display:flex;justify-content:flex-end;flex:0 0 auto}
.idopill{font-variant-numeric:tabular-nums;font-weight:700;font-size:12.5px;padding:3px 8px;border-radius:7px}
.custcol{width:74px;text-align:right;font-variant-numeric:tabular-nums;font-weight:600;font-size:14px;flex:0 0 auto}
.note{color:var(--muted);font-size:12px;margin:14px 2px 0;max-width:680px}

.addwrap{position:relative}
.addinput{font-size:13px;padding:8px 13px;border:1px dashed rgba(26,24,19,.28);border-radius:999px;background:transparent;color:var(--ink);width:210px}
.addmenu{position:absolute;top:100%;right:0;margin-top:6px;width:240px;background:#fff;border:1px solid rgba(26,24,19,.12);border-radius:12px;box-shadow:0 16px 40px -12px rgba(26,24,19,.3);z-index:40;padding:6px;max-height:44vh;overflow:auto}
.additem{display:flex;align-items:center;gap:9px;width:100%;padding:8px 9px;border-radius:8px;font-size:13.5px;background:none;border:0;cursor:pointer;text-align:left}
.additem:hover{background:#f2efe7}
.miniflag{width:20px;height:14px;border-radius:2px;object-fit:cover;box-shadow:0 0 0 .5px rgba(26,24,19,.2)}
.empty{border:1px dashed rgba(26,24,19,.2);border-radius:16px;padding:44px 24px;text-align:center;color:var(--muted)}
.empty .et{font-family:var(--serif);font-size:19px;color:var(--ink2);margin-bottom:6px}
.linka{color:var(--acc);font-weight:600;background:none;border:0;cursor:pointer;margin:0 4px}

.ccards{display:grid;gap:12px;margin-bottom:18px}
.ccard{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 15px;border-top:3px solid var(--c)}
.ccard .ch{display:flex;align-items:center;gap:10px}
.ccard .cn{font-weight:700;font-size:15px;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cstats{display:flex;gap:18px;margin-top:12px}
.cstats .l{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);font-weight:700}
.cstats .v{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.cgames{margin-top:12px;border-top:1px solid var(--line);padding-top:9px}
.cgames .l{font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint);font-weight:700;margin-bottom:6px}
.chipset{display:flex;flex-wrap:wrap;gap:5px}
.gchip{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;padding:3px 7px;border-radius:7px;cursor:pointer;background:var(--surface)}
.gchip img{width:15px;height:11px;border-radius:1px;object-fit:cover}
.gchip.off{color:var(--faint);border:1px dashed rgba(26,24,19,.2);text-decoration:line-through;background:transparent;font-weight:400}
.gchip.off img{opacity:.4}

.confronto{display:flex;align-items:center;gap:14px;background:var(--ink);color:var(--page);border-radius:14px;padding:15px 18px;margin-bottom:22px;flex-wrap:wrap}
.confronto .cl{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:#b3ad9c;font-weight:700;flex:0 0 auto}
.confronto .mid{display:inline-flex;align-items:center;gap:9px}
.confronto .mid .fl{width:26px;height:18px;border-radius:3px;object-fit:cover}
.confronto .st{font-family:var(--serif);font-size:20px}
.confronto .num{font-weight:800;font-size:20px;color:#7fd0a3;font-variant-numeric:tabular-nums}
.confronto .by{color:#8f8a7e;font-size:12px;flex:1;text-align:right;min-width:120px}
.confronto .sub{color:#b3ad9c;font-size:13px}

.cmp{display:grid;grid-template-columns:340px 1fr;gap:26px;align-items:start}
.radarcard{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:18px 16px 8px;position:sticky;top:74px}
.rt{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:700;text-align:center;margin-bottom:4px}
.rcenter{display:flex;justify-content:center}
.legend{display:flex;flex-direction:column;gap:6px;margin-top:8px}
.legend .li{display:flex;align-items:center;gap:8px;font-size:13px}
.legend .sw{width:12px;height:3px;border-radius:2px}
.dimtbl{margin-top:13px;border-top:1px solid var(--line);padding-top:11px}
.dimtbl .h{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);font-weight:700;margin-bottom:7px}
.dimrow{display:flex;align-items:center;gap:8px;padding:3px 0;font-size:12.5px}
.dimrow .dn{flex:1;color:var(--ink2)}
.qm{display:inline-flex;align-items:center;justify-content:center;width:13px;height:13px;margin-left:5px;border-radius:50%;border:1px solid var(--faint);color:var(--muted);font-size:9px;line-height:1;font-weight:700;cursor:help;vertical-align:1px}
.qm:hover{color:var(--ink2);border-color:var(--ink2)}
.dimrow .ds{width:36px;text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.dimnote{font-size:10.5px;color:var(--faint);margin-top:8px;line-height:1.45}
.grphead{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint);font-weight:700;margin:4px 2px 10px}
.mrow{margin-bottom:16px}
.mlbl{font-size:13px;color:var(--ink2);font-weight:500;margin-bottom:6px}
.barline{display:flex;align-items:center;gap:10px;margin-bottom:4px}
.track{flex:1;height:14px;background:#eae6db;border-radius:5px;overflow:hidden}
.track.sm{height:8px}
.fill{display:block;height:100%;border-radius:5px}
.bnum{width:58px;text-align:right;font-variant-numeric:tabular-nums;font-size:13.5px}

.phead{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:20px}
.pid{display:flex;align-items:center;gap:16px}
.pflag{width:64px;height:44px;border-radius:5px;object-fit:cover;box-shadow:0 0 0 .5px rgba(26,24,19,.22),0 6px 16px -8px rgba(26,24,19,.4)}
.pname{font-family:var(--serif);font-size:32px;font-weight:500;line-height:1;letter-spacing:-.01em}
.psub{color:var(--muted);font-size:13px;margin-top:5px}
.psub b{color:var(--acc)}
.backbtn{cursor:pointer;font-size:12.5px;font-weight:600;color:var(--ink2);border:1px solid rgba(26,24,19,.16);border-radius:9px;padding:8px 13px;background:transparent}
.hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:24px}
.hcard{background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:14px 15px}
.hcard.ife{border-left:3px solid var(--acc)} .hcard.ido{border-left:3px solid var(--ora)}
.hcard .hl{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);font-weight:700}
.hcard .hv{font-size:28px;font-weight:800;font-variant-numeric:tabular-nums;margin-top:2px;letter-spacing:-.01em}
.hcard.plain .hv{font-size:24px;font-weight:700}
.hcard .hn{font-size:11px;color:var(--muted);margin-top:1px}
.pbody{display:grid;grid-template-columns:320px 1fr;gap:26px;align-items:start}
.gtoggle{display:flex;flex-direction:column;gap:7px}
.grow{display:flex;align-items:center;gap:10px;border-radius:11px;padding:9px 11px;cursor:pointer;border:1px solid var(--line);background:var(--surface);width:100%;text-align:left}
.grow.off{background:transparent;border-style:dashed;border-color:rgba(26,24,19,.16)}
.gcheck{width:17px;height:17px;flex:0 0 auto;border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;color:#fff}
.gbadge{width:20px;height:20px;flex:0 0 auto;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:10.5px;font-weight:700;color:#fff}
.gmid{flex:1;min-width:0}
.gmid .op{font-size:11px;color:var(--faint)}
.gmid .on{font-weight:600;font-size:13.5px}
.gscore{font-weight:700;font-size:16px;font-variant-numeric:tabular-nums}
.mgroups .grphead2{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:#b3ad9c;font-weight:700;margin:14px 2px 8px}
.statrow{display:grid;grid-template-columns:168px 1fr 66px 52px;align-items:center;gap:12px;padding:7px 2px;border-bottom:1px solid rgba(26,24,19,.06)}
.statrow .sl{font-size:13px;color:var(--ink2)}
.statrow .sv{text-align:right;font-weight:700;font-variant-numeric:tabular-nums;font-size:14px}
.statrow .sr{text-align:right;font-variant-numeric:tabular-nums;font-weight:700;font-size:12.5px}
.picker{display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:8px}
.pk{display:flex;align-items:center;gap:10px;padding:11px 12px;background:var(--surface);border:1px solid var(--line);border-radius:11px;cursor:pointer;text-align:left}
.pk:hover{border-color:rgba(47,125,85,.55);background:#fff}
.pk .pkn{font-weight:600;font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pk .pks{font-size:11px;color:var(--faint)}
.search{font-size:14px;padding:11px 14px;border:1px solid rgba(26,24,19,.14);border-radius:11px;background:var(--surface);color:var(--ink);width:280px;max-width:100%;margin-bottom:18px}
.skel{height:46px;background:#e6e2d7;border-radius:10px;margin-bottom:10px;animation:shimmer 1.4s ease-in-out infinite}
@media (max-width:820px){
  .explain{grid-template-columns:1fr}
  .cmp,.pbody{grid-template-columns:1fr}
  .radarcard{position:static}
  .ifetrack{width:96px}
}
</style>
</head>
<body>
<div class="wrap"><div id="app"></div></div>

<script id="viz-data" type="application/json">__DATA__</script>
<script>
"use strict";
/* ============================================================
   Estatísticas Copa 2026 — redesign (vanilla, offline).
   Lê o payload JSON embutido em #viz-data. Em dev, se o placeholder
   do template não foi substituído, busca data/wc.json.
   Índices IDO/IFE vêm prontos; as 5 dimensões compostas são
   z-scores calculados no cliente (régua global fixa). Se o payload
   trouxer dims/dimsBaseline (spec canônica do pipeline Python),
   eles substituem a spec/régua locais.
   ============================================================ */
var DATA, FLAGS, GAMES, TEAMS, GROUPS, PHASES, DESC, IFE_MKT, IFE_SHRINK, OPP, BASE;
var app = document.getElementById('app');

var PAL = ['#c0392b','#2f6fb0','#c8781c','#6b4bb0'];
var ACC='#2f7d55', RED='#c0392b', ORA='#c8781c';
var IDX = ['IFE','IDO','P(Vitória %)','xGD'];

/* dimensão: [métrica, peso, inverter?]. '@' = derivada por jogo. Fallback:
   se o payload trouxer DATA.dims (spec canônica do Python), ela substitui. */
var DIMS = [
  {name:'Ataque',      comps:[['xG (Gols Esperados)',.40],['Grandes Chances',.25],['Chutes no Alvo',.20],['Finalizações',.15]]},
  {name:'Finalização', comps:[['Gols − xG',.40],['@xg_por_fin',.30],['Grandes Chances Convertidas',.30]]},
  {name:'Controle',    comps:[['Posse de Bola (%)',.35],['Passes Certos',.30],['Entradas no Último Terço',.35]]},
  {name:'Pressão',     comps:[['Toques na Área',.40],['Ações no Último Terço',.30],['Faltas Sofridas no Último Terço',.30]]},
  {name:'Defesa',      comps:[['xG Concedido',.45,true],['Grandes Chances Concedidas',.30,true],['Gols Evitados',.15],['Duelos Ganhos (%)',.10]]}
];
/* tooltips das dimensões do radar (chave = nome da dimensão) */
var DIM_TIPS = {
  'Ataque':'Quanto o time cria: xG, grandes chances, chutes no alvo e finalizações.',
  'Finalização':'Quanto o time converte o que cria: gols acima/abaixo do xG, xG por finalização e grandes chances convertidas.',
  'Controle':'Controle do jogo com a bola: posse, passes certos e chegada ao terço final.',
  'Pressão':'Quanto o time joga no campo do adversário: toques na área, ações no último terço e faltas sofridas lá.',
  'Defesa':'Quanto o time cede: xG e grandes chances concedidos (menos = melhor), gols evitados e duelos ganhos.'
};
/* grupos curados do Comparar/Perfil (o expansor mostra o resto do payload) */
var CB = [
  {name:'Ataque',        metrics:['xG (Gols Esperados)','Grandes Chances','Chutes no Alvo','Finalizações','Toques na Área']},
  {name:'Eficiência',    metrics:['Gols','Gols − xG','Grandes Chances Convertidas']},
  {name:'Defesa',        metrics:['Gols Sofridos','xG Concedido','Grandes Chances Concedidas','Gols Evitados']},
  {name:'Posse & Passe', metrics:['Posse de Bola (%)','Passes Certos','Entradas no Último Terço','Duelos Ganhos (%)']}
];
/* métricas em que MENOR é melhor: ranking, destaque e ordenação invertem */
var INV = {'Gols Sofridos':1,'xG Concedido':1,'Grandes Chances Concedidas':1};

var state = {
  mode:'painel', phase:'all', sortKey:'IFE', customMetric:null,
  metricMenuOpen:false, metricQuery:'', agg:'media', showAllMetrics:false,
  compare:[], compareQuery:'', team:null, teamQuery:'', excluded:new Set()
};

/* ---------- helpers de dados ---------- */
function fmt(v){ if(v==null||v!==v) return '–'; return Number.isInteger(v)? v.toLocaleString('pt-BR') : v.toLocaleString('pt-BR',{maximumFractionDigits:2}); }
function signed(v,dec){ if(v==null||v!==v) return '–'; var a=Math.abs(v); var s=dec===0? Math.round(a).toLocaleString('pt-BR'): a.toLocaleString('pt-BR',{maximumFractionDigits:2}); return (v>0?'+':v<0?'−':'')+s; }
function disp(label,v){ if(v==null) return '–'; if(label==='IFE'||label==='xGD'||label==='Gols − xG') return signed(v,2); if(label==='IDO') return signed(v,0); return fmt(v)+(label.indexOf('(%)')>=0?'%':''); }
function short(l){ return l.replace(' (Gols Esperados)','').replace(' (%)','').replace(' (certos)','').replace(' (ganhos)','').replace(' do Goleiro',''); }
function tip(l){ return (DESC && DESC[l]) || ''; }
/* ícone "?" com tooltip (padrão do app); vazio se não houver texto */
function qm(txt){ return txt? '<span class="qm" title="'+esc(txt)+'">?</span>' : ''; }
function flag(t){ return FLAGS[t] || ''; }
function fimg(t,cls){ var f=flag(t); return f? '<img class="'+(cls||'flag')+'" src="'+f+'" alt="">' : ''; }
function signColor(v){ return v==null? 'var(--muted)' : v>0.001? 'var(--acc)' : v<-0.001? 'var(--red)' : '#6b665b'; }
function lerp(a,b,t){ t=Math.max(0,Math.min(1,t)); function p(h){return [1,3,5].map(function(i){return parseInt(h.slice(i,i+2),16);});} var A=p(a),B=p(b); return 'rgb('+A.map(function(x,i){return Math.round(x+(B[i]-x)*t);}).join(',')+')'; }
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;'); }
/* busca sem acentos/caixa: "franca" acha "França" */
function norm(s){ return String(s).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,''); }

function phaseGames(){ return state.phase==='all'? GAMES : GAMES.filter(function(g){return g.fase===state.phase;}); }
function teamPhaseGames(t){ return phaseGames().filter(function(g){return g.selecao===t;}); }
function gkey(g){ return g.selecao+'|'+g.event_id; }
function teamGames(t){ return teamPhaseGames(t).filter(function(g){return !state.excluded.has(gkey(g));}); }
function teamsInPhase(){ var s={}; phaseGames().forEach(function(g){s[g.selecao]=1;}); return Object.keys(s).sort(function(a,b){return a.localeCompare(b,'pt-BR');}); }
function aggregate(games,label){ var vs=games.map(function(g){return g.values[label];}).filter(function(v){return v!=null;}); if(!vs.length) return null; var sum=vs.reduce(function(a,b){return a+b;},0); var mean=label.indexOf('(%)')>=0||IDX.indexOf(label)>=0; if(mean||state.agg==='media') return Math.round(sum/vs.length*100)/100; return Math.round(sum*100)/100; }
function meanOf(games,label){ var vs=games.map(function(g){return g.values[label];}).filter(function(v){return v!=null;}); if(!vs.length) return null; return vs.reduce(function(a,b){return a+b;},0)/vs.length; }
function ifeOf(t){ var mkt=IFE_MKT[t]; if(mkt==null) return null; var res=teamGames(t).map(function(g){return g.ifeRes;}).filter(function(v){return v!=null;}); var n=res.length; if(!n) return Math.round(mkt*100)/100; var m=res.reduce(function(a,b){return a+b;},0)/n; return Math.round((mkt+m*n/(n+IFE_SHRINK))*100)/100; }
function idoOf(t){ var v=meanOf(teamGames(t),'IDO'); return v==null?null:Math.round(v*100)/100; }
function valueFor(t,label){ if(label==='IFE') return ifeOf(t); if(label==='IDO') return idoOf(t); return aggregate(teamGames(t),label); }
function record(t){ var w=0,d=0,l=0,gf=0,ga=0; teamGames(t).forEach(function(g){ var m=/^(-?\d+)-(-?\d+)/.exec(g.placar||''); if(!m) return; var a=+m[1],b=+m[2]; gf+=a;ga+=b; if(a>b)w++; else if(a<b)l++; else d++; }); return {w:w,d:d,l:l,gf:gf,ga:ga,pts:w*3+d,games:w+d+l}; }
function phaseReached(t){ var set={}; GAMES.filter(function(g){return g.selecao===t;}).forEach(function(g){set[g.fase]=1;}); for(var i=PHASES.length-1;i>=0;i--) if(set[PHASES[i]]) return PHASES[i]; return '—'; }
function ordinal(t,label){ var arr=teamsInPhase().map(function(x){return {x:x,v:valueFor(x,label)};}).filter(function(o){return o.v!=null;}).sort(function(a,b){return INV[label]? a.v-b.v : b.v-a.v;}); var i=-1; for(var k=0;k<arr.length;k++) if(arr[k].x===t){i=k;break;} return {rank:i<0?null:i+1,n:arr.length,pct:i<0?0:(arr.length>1?(arr.length-1-i)/(arr.length-1):1)}; }
function toggleGame(t,eid){ var k=t+'|'+eid; if(state.excluded.has(k)) state.excluded.delete(k); else state.excluded.add(k); render(); }

/* ---------- dimensões (z-score, régua global) ---------- */
function buildIndex(){
  OPP={}; GAMES.forEach(function(r){ (OPP[r.event_id]=OPP[r.event_id]||{})[r.selecao]=r.values; });
  var keys={}; DIMS.forEach(function(d){d.comps.forEach(function(c){keys[c[0]]=1;});});
  BASE={};
  Object.keys(keys).forEach(function(k){
    var vs=GAMES.map(function(r){return compVal(r,k);}).filter(function(v){return v!=null;});
    if(!vs.length){ BASE[k]={mean:0,sd:1}; return; }
    var mean=vs.reduce(function(a,b){return a+b;},0)/vs.length;
    var sd=Math.sqrt(vs.reduce(function(a,b){return a+(b-mean)*(b-mean);},0)/vs.length)||1;
    BASE[k]={mean:mean,sd:sd};
  });
}
function compVal(row,key){
  var V=row.values;
  var f=V['Finalizações'];
  if(key==='@xg_por_fin'){ var x=V['xG (Gols Esperados)']; return (f&&x!=null)? x/f : null; }
  if(V[key]!=null) return V[key];
  /* fallbacks p/ payloads sem as colunas canônicas: gols saem do placar,
     concedidos caem para a linha do adversário no mesmo jogo */
  var m=/^(-?\d+)-(-?\d+)/.exec(row.placar||'');
  if(key==='Gols') return m? +m[1] : null;
  if(key==='Gols Sofridos') return m? +m[2] : null;
  if(key==='Gols − xG'){ var xg=V['xG (Gols Esperados)']; return (m&&xg!=null)? +m[1]-xg : null; }
  var opp=OPP[row.event_id]&&OPP[row.event_id][row.adversario]; if(!opp) return null;
  if(key==='xG Concedido') return opp['xG (Gols Esperados)'];
  if(key==='Grandes Chances Concedidas') return opp['Grandes Chances'];
  return null;
}
function dimZ(t,dim){
  var gs=teamGames(t), num=0, den=0;
  dim.comps.forEach(function(c){
    var b=BASE[c[0]]; if(!b||!b.sd) return;
    var vs=gs.map(function(g){return compVal(g,c[0]);}).filter(function(v){return v!=null;});
    if(!vs.length) return;
    var agg=vs.reduce(function(a,x){return a+x;},0)/vs.length;
    var z=(agg-b.mean)/b.sd; if(c[2]) z=-z;
    num+=z*c[1]; den+=c[1];
  });
  return den>0? num/den : null;
}
function dimScore(t,dim){ var z=dimZ(t,dim); return z==null?null:Math.max(0,Math.min(100,Math.round(50+15*z))); }

/* ---------- radar (SVG string) ---------- */
function radarSVG(sel){
  var R=90,cx=150,cy=124,N=DIMS.length;
  function ang(i){ return (-90+i*360/N)*Math.PI/180; }
  var out='<svg viewBox="0 0 300 248" style="width:100%;max-width:300px;height:auto;overflow:visible">';
  [0.25,0.5,0.75,1].forEach(function(f){ out+='<circle cx="'+cx+'" cy="'+cy+'" r="'+(R*f)+'" fill="none" stroke="rgba(26,24,19,.09)"/>'; });
  DIMS.forEach(function(dim,i){ var c=Math.cos(ang(i)),s=Math.sin(ang(i)); var lx=cx+(R+17)*c,ly=cy+(R+17)*s;
    out+='<line x1="'+cx+'" y1="'+cy+'" x2="'+(cx+R*c).toFixed(1)+'" y2="'+(cy+R*s).toFixed(1)+'" stroke="rgba(26,24,19,.09)"/>';
    out+='<text x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'" text-anchor="middle" dominant-baseline="middle" font-size="10" font-family="Archivo" font-weight="600" fill="#6b665b" style="cursor:help">'+dim.name+(DIM_TIPS[dim.name]?'<title>'+esc(DIM_TIPS[dim.name])+'</title>':'')+'</text>';
  });
  sel.forEach(function(t,idx){
    var pts=DIMS.map(function(dim,i){ var z=dimZ(t,dim); var n=z==null?0.03:(z+2.5)/5; n=Math.max(0.03,Math.min(1,n)); return (cx+R*n*Math.cos(ang(i))).toFixed(1)+','+(cy+R*n*Math.sin(ang(i))).toFixed(1); }).join(' ');
    var c=PAL[idx%PAL.length];
    out+='<polygon points="'+pts+'" fill="'+c+'26" stroke="'+c+'" stroke-width="2" stroke-linejoin="round"/>';
  });
  return out+'</svg>';
}

/* ---------- render ---------- */
function render(){
  var activeAct=document.activeElement&&document.activeElement.dataset?document.activeElement.dataset.act:null;
  var caret=null; try{caret=document.activeElement.selectionStart;}catch(e){}
  app.innerHTML = renderHead()+renderToolbar()+renderView();
  if(activeAct){ var el=app.querySelector('input[data-act="'+activeAct+'"]'); if(el){ el.focus(); try{el.setSelectionRange(caret,caret);}catch(e){} } }
}

function renderHead(){
  var nm=new Set(GAMES.map(function(g){return g.event_id;})).size;
  var nt=new Set(GAMES.map(function(g){return g.selecao;})).size;
  return '<div class="head"><div>'+
    '<div class="kicker"><span class="dot8"></span>Avaliação de seleções · para o bolão</div>'+
    '<h1>Copa do Mundo 2026<span class="dim"> · Estatísticas</span></h1></div>'+
    '<div class="metaR"><div><b>'+nm+' jogos · '+nt+' seleções</b></div><div>atualizado em '+(DATA.generatedAt||'')+'</div></div></div>';
}

function renderToolbar(){
  var modes=[['painel','Painel'],['compare','Comparar'],['team','Perfil']].map(function(m){ return '<button data-act="mode:'+m[0]+'" class="'+(state.mode===m[0]?'on':'')+'">'+m[1]+'</button>'; }).join('');
  var chips=[['all','Todas']].concat(PHASES.map(function(p){return [p,p];})).map(function(p){ return '<button class="chip '+(state.phase===p[0]?'on':'')+'" data-act="phase:'+esc(p[0])+'">'+p[1]+'</button>'; }).join('');
  var restore = state.excluded.size? '<button class="restore" data-act="restoreAll" title="Voltar a considerar todos os jogos">↺ '+state.excluded.size+' jogo(s) ocultos · restaurar</button>' : '';
  return '<div class="toolbar"><div class="tools">'+
    '<div class="seg">'+modes+'</div><div class="vr"></div>'+
    '<div class="chips"><span class="tlabel">Fase</span>'+chips+'</div>'+restore+'</div></div>';
}

function renderView(){
  if(state.mode==='painel') return renderPainel();
  if(state.mode==='compare') return renderCompare();
  return renderTeam();
}

/* ---- Painel ---- */
function renderPainel(){
  var teams=teamsInPhase();
  var rows=teams.map(function(t){ return {t:t, ife:ifeOf(t), ido:idoOf(t), cust:state.customMetric?valueFor(t,state.customMetric):null, n:teamGames(t).length}; });
  var sk=state.sortKey;
  rows.sort(function(a,b){ var va=sk==='IFE'?a.ife:sk==='IDO'?a.ido:a.cust, vb=sk==='IFE'?b.ife:sk==='IDO'?b.ido:b.cust;
    if(va==null&&vb==null) return 0; if(va==null) return 1; if(vb==null) return -1;
    return INV[sk]? va-vb : vb-va; });
  var maxAbs=Math.max(0.01); rows.forEach(function(r){ if(r.ife!=null) maxAbs=Math.max(maxAbs,Math.abs(r.ife)); });

  var body=rows.map(function(r,i){
    var pos=r.ife!=null&&r.ife>=0, w=r.ife==null?0:Math.abs(r.ife)/maxAbs*50;
    var fillCss=pos? 'left:50%;width:'+w+'%;background:var(--acc);border-radius:0 4px 4px 0' : 'right:50%;width:'+w+'%;background:var(--red);border-radius:4px 0 0 4px';
    var idoCss = r.ido==null?'color:var(--faint);background:rgba(26,24,19,.05)':r.ido>0.5?'color:var(--acc);background:rgba(47,125,85,.12)':r.ido<-0.5?'color:var(--red);background:rgba(192,57,43,.1)':'color:#6b665b;background:rgba(26,24,19,.05)';
    var cust = state.customMetric? '<span class="custcol">'+disp(state.customMetric,r.cust)+'</span>' : '';
    return '<button class="brow" data-act="team:'+esc(r.t)+'">'+
      '<span class="rank">'+(i+1)+'</span>'+fimg(r.t)+
      '<span class="bname"><span class="nm">'+r.t+'</span><span class="sub">'+r.n+(r.n===1?' jogo':' jogos')+'</span></span>'+
      '<span class="ifetrack"><span class="ifecenter"></span><span class="ifefill" style="'+fillCss+'"></span></span>'+
      '<span class="ifeval" style="color:'+signColor(r.ife)+'">'+signed(r.ife,2)+'</span>'+
      '<span class="idowrap"><span class="idopill" style="'+idoCss+'">'+signed(r.ido,0)+'</span></span>'+cust+'</button>';
  }).join('');

  var sortLbl = sk==='IFE'?'força (IFE)':sk==='IDO'?'desempenho vs odds (IDO)':short(state.customMetric);
  var sortSeg='<div class="seg sm">'+[['IFE','IFE'],['IDO','IDO']].map(function(a){return '<button class="'+(sk===a[0]?'on':'')+'" data-act="sort:'+a[0]+'">'+a[1]+'</button>';}).join('')+'</div>';
  var custBtn='<button class="custbtn '+(state.customMetric?'on':'')+'" data-act="toggleMetricMenu">'+(state.customMetric?short(state.customMetric):'+ outra métrica ▾')+'</button>'+(state.customMetric?'<button class="xbtn" data-act="clearCustom" title="Remover">×</button>':'');
  var menu = state.metricMenuOpen? renderMetricMenu() : '';
  var custHead = state.customMetric? '<span style="width:74px;text-align:right">'+short(state.customMetric)+'</span>' : '';

  return '<section>'+
    '<div class="explain">'+
      '<div class="exc ife" title="'+esc(tip('IFE'))+'"><h4>IFE · Índice de Força da Equipe</h4><p>Força numa régua única — saldo de xG por jogo contra um adversário médio. A diferença de IFE entre duas seleções projeta o placar de xG de um confronto direto.</p></div>'+
      '<div class="exc ido" title="'+esc(tip('IDO'))+'"><h4>IDO · Índice de Desempenho vs Odds</h4><p>Quanto a seleção rendeu acima (+) ou abaixo (−) do que as odds pré-jogo previam. Mede surpresa, não força bruta.</p></div>'+
    '</div>'+
    '<div class="sechead"><div><div class="overline">Painel de força · todas as seleções</div><div class="title">Ordenado por '+sortLbl+'</div></div>'+
      '<div class="rowctrl">'+sortSeg+'<div class="addwrap">'+custBtn+menu+'</div></div></div>'+
    '<div class="collbl"><span style="width:26px"></span><span style="width:26px"></span><span style="flex:1">Seleção</span><span style="width:150px;text-align:center">IFE · força</span><span style="width:62px;text-align:right">IFE</span><span style="width:66px;text-align:right">IDO</span>'+custHead+'</div>'+
    '<div class="board">'+body+'</div>'+
    '<p class="note">Barra verde/vermelha = IFE acima/abaixo da média da Copa. Filtre por fase acima, ou abra o <strong>Perfil</strong> de uma seleção para incluir/excluir jogos — todos os índices recalculam. Clique numa seleção para ver o perfil.</p>'+
  '</section>';
}

function renderMetricMenu(){
  var q=norm(state.metricQuery.trim());
  var html='<div class="menu" style="right:0"><div class="mh"><input data-act="q:metric" value="'+esc(state.metricQuery)+'" placeholder="buscar métrica…"></div><div class="ml">';
  GROUPS.forEach(function(g){
    var sts=g.stats.filter(function(l){ return IDX.indexOf(l)<0 && (!q||norm(l).indexOf(q)>=0); });
    if(!sts.length) return;
    html+='<div class="mgrp">'+g.name+'</div>';
    sts.forEach(function(l){ html+='<button class="mitem '+(l===state.customMetric?'on':'')+'" data-act="pickMetric:'+esc(l)+'">'+l+'</button>'; });
  });
  return html+'</div></div>';
}

/* ---- Comparar ---- */
function renderCompare(){
  var teams=teamsInPhase();
  var sel=state.compare.filter(function(t){return teams.indexOf(t)>=0;});
  /* Soma × Média/jogo (percentuais e índices são sempre média) — só faz
     sentido com barras na tela, i.e. 2+ seleções */
  var aggSeg=sel.length>=2? '<div class="seg sm" title="Como agregar as contagens dos jogos considerados. Percentuais e índices (IFE, IDO, P de vitória, xGD) são sempre média.">'+
    [['media','Média/jogo'],['soma','Soma']].map(function(a){return '<button class="'+(state.agg===a[0]?'on':'')+'" data-act="agg:'+a[0]+'">'+a[1]+'</button>';}).join('')+'</div>' : '';
  var titleRow='<div class="sechead"><div class="title lg">Comparar seleções</div><div class="rowctrl">'+aggSeg+
    (sel.length<4? '<div class="addwrap"><input class="addinput" data-act="q:compare" value="'+esc(state.compareQuery)+'" placeholder="+ adicionar seleção">'+renderAddMenu(teams,sel)+'</div>':'')+'</div></div>';

  var sug=['Brasil','Argentina','França','Espanha','Inglaterra','Portugal'].filter(function(t){return teams.indexOf(t)>=0&&sel.indexOf(t)<0;}).slice(0,3);
  var sugH=sug.map(function(t){return '<button class="linka" data-act="addCompare:'+esc(t)+'">'+t+'</button>';}).join('');
  if(!sel.length){
    return '<section>'+titleRow+'<div class="empty"><div class="et">Escolha duas seleções para comparar</div><div>Sugestões: '+sugH+'</div></div></section>';
  }

  var cards=sel.map(function(t,i){
    var col=PAL[i%PAL.length], ife=ifeOf(t), ido=idoOf(t), pg=teamPhaseGames(t);
    var chips=pg.map(function(g){ var ex=state.excluded.has(gkey(g)); var pl=(g.placar||'').split(' ')[0];
      return '<button class="gchip '+(ex?'off':'')+'" '+(ex?'':'style="background:'+col+'14;border:1px solid '+col+'44"')+' data-act="toggleGame:'+esc(t)+'|'+g.event_id+'" title="'+(ex?'incluir':'excluir')+' · vs '+esc(g.adversario)+' ('+g.fase+')">'+fimg(g.adversario,'')+pl+'</button>';
    }).join('');
    return '<div class="ccard" style="--c:'+col+'"><div class="ch">'+fimg(t,'flag')+'<span class="cn">'+t+'</span><button class="xbtn" data-act="removeCompare:'+esc(t)+'">×</button></div>'+
      '<div class="cstats"><div><div class="l">IFE'+qm(tip('IFE'))+'</div><div class="v" style="color:'+signColor(ife)+'">'+signed(ife,2)+'</div></div>'+
      '<div><div class="l">IDO médio'+qm(tip('IDO'))+'</div><div class="v" style="color:'+signColor(ido)+'">'+signed(ido,0)+'</div></div></div>'+
      '<div class="cgames"><div class="l">Jogos considerados · '+teamGames(t).length+'/'+pg.length+'</div><div class="chipset">'+chips+'</div></div></div>';
  }).join('');

  /* 1 seleção: mostra o card dela e convida a adicionar a segunda */
  if(sel.length===1){
    var ph='<div class="empty" style="display:flex;flex-direction:column;justify-content:center;gap:6px;padding:24px;border-radius:14px">'+
      '<div class="et" style="font-size:17px">Adicione mais uma seleção</div>'+
      '<div>para comparar com '+sel[0]+' — use a busca acima'+(sugH?', ou:'+sugH:'')+'</div></div>';
    return '<section>'+titleRow+'<div class="ccards" style="grid-template-columns:1fr 1fr">'+cards+ph+'</div></section>';
  }

  var confronto='';
  if(sel.length===2){ var ia=ifeOf(sel[0]),ib=ifeOf(sel[1]); if(ia!=null&&ib!=null){ var diff=Math.round((ia-ib)*100)/100; var st=diff>=0?sel[0]:sel[1];
    confronto='<div class="confronto"><span class="cl">Projeção de confronto direto</span><span class="mid">'+fimg(st,'fl')+'<span class="st">'+st+'</span><span class="num">+'+fmt(Math.abs(diff))+'</span><span class="sub">de saldo de xG esperado</span></span><span class="by">pela diferença de IFE</span></div>'; } }

  var legend=sel.map(function(t,i){return '<div class="li"><span class="sw" style="background:'+PAL[i%PAL.length]+'"></span>'+fimg(t,'miniflag')+'<span style="font-weight:600">'+t+'</span></div>';}).join('');
  var dimtbl=DIMS.map(function(dim){
    var scores=sel.map(function(t){return dimScore(t,dim);});
    var best=Math.max.apply(null,[-1].concat(scores.map(function(s){return s==null?-1:s;})));
    var cells=sel.map(function(t,i){ var s=scores[i]; return '<span class="ds" style="font-weight:'+(s===best&&best>0?'800':'600')+';color:'+PAL[i%PAL.length]+'">'+(s==null?'–':s)+'</span>'; }).join('');
    return '<div class="dimrow"><span class="dn">'+dim.name+qm(DIM_TIPS[dim.name])+'</span>'+cells+'</div>';
  }).join('');

  function barGroups(list){
    return list.map(function(g){
      var rows=g.metrics.map(function(label){
        var cells=sel.map(function(t,i){return {v:aggregate(teamGames(t),label),color:PAL[i%PAL.length]};});
        var mx=Math.max.apply(null,cells.map(function(c){return c.v||0;}));
        /* em métricas invertidas (menor=melhor) o destaque vai ao MENOR valor */
        var lead=INV[label]? Math.min.apply(null,cells.map(function(c){return c.v==null?1e9:c.v;}))
                           : Math.max.apply(null,cells.map(function(c){return c.v==null?-1e9:c.v;}));
        var cellsH=cells.map(function(c){ var w=(mx>0&&c.v!=null&&c.v>=0)?Math.max(3,c.v/mx*100):0; var isL=c.v!=null&&c.v===lead;
          return '<div class="barline"><span class="track"><span class="fill" style="width:'+w+'%;background:'+c.color+';opacity:'+(isL?1:.62)+'"></span></span><span class="bnum" style="font-weight:'+(isL?'700':'500')+';color:'+(isL?c.color:'#6b665b')+'">'+disp(label,c.v)+'</span></div>';
        }).join('');
        return '<div class="mrow"><div class="mlbl">'+label+qm(tip(label))+'</div>'+cellsH+'</div>';
      }).join('');
      return '<div class="grphead">'+g.name+'</div>'+rows;
    }).join('');
  }
  var bars=barGroups(CB);
  var extras=extraGroups();
  var moreBtn=extras.length? '<div style="margin:2px 0 14px"><button class="custbtn '+(state.showAllMetrics?'on':'')+'" data-act="toggleAllMetrics">'+(state.showAllMetrics?'ocultar métricas extras ▴':'ver todas as métricas ▾')+'</button></div>' : '';
  var moreBars=state.showAllMetrics? barGroups(extras) : '';

  return '<section>'+titleRow+
    '<div class="ccards" style="grid-template-columns:repeat('+sel.length+',1fr)">'+cards+'</div>'+confronto+
    '<div class="cmp"><div class="radarcard"><div class="rt">Perfil de jogo comparado</div><div class="rcenter">'+radarSVG(sel)+'</div>'+
      '<div class="legend">'+legend+'</div>'+
      '<div class="dimtbl"><div class="h">Dimensões · escore 0–100</div>'+dimtbl+'<div class="dimnote">50 = média da Copa · calculadas sempre sobre a MÉDIA POR JOGO dos jogos selecionados (o seletor Soma/Média não as afeta)</div></div>'+
    '</div><div>'+bars+moreBtn+moreBars+'</div></div></section>';
}
/* grupos do payload ainda não exibidos na curadoria (menos os índices) */
function extraGroups(){
  var shown={}; CB.forEach(function(g){g.metrics.forEach(function(m){shown[m]=1;});});
  IDX.forEach(function(m){shown[m]=1;});
  var out=[];
  GROUPS.forEach(function(g){
    var ms=g.stats.filter(function(m){return !shown[m];});
    if(ms.length) out.push({name:g.name, metrics:ms});
  });
  return out;
}
function renderAddMenu(teams,sel){
  var q=norm(state.compareQuery.trim()); if(!q) return '';
  var res=teams.filter(function(t){return sel.indexOf(t)<0&&norm(t).indexOf(q)>=0;}).slice(0,8);
  if(!res.length) return '';
  return '<div class="addmenu">'+res.map(function(t){return '<button class="additem" data-act="addCompare:'+esc(t)+'">'+fimg(t,'miniflag')+t+'</button>';}).join('')+'</div>';
}

/* ---- Perfil ---- */
function renderTeam(){
  var teams=teamsInPhase();
  if(!state.team){
    var q=norm(state.teamQuery.trim());
    var list=teams.filter(function(t){return !q||norm(t).indexOf(q)>=0;}).map(function(t){ var r=record(t);
      return '<button class="pk" data-act="team:'+esc(t)+'">'+fimg(t,'flag')+'<span class="bname"><span class="pkn">'+t+'</span><span class="pks">IFE '+signed(ifeOf(t),2)+'</span></span></button>'; }).join('');
    return '<section><div class="title lg">Perfil da seleção</div><div class="psub" style="margin:4px 0 16px">Escolha uma seleção para avaliar força (IFE), desempenho vs odds (IDO), jogos e ranking em cada métrica.</div>'+
      '<input class="search" data-act="q:team" value="'+esc(state.teamQuery)+'" placeholder="buscar seleção…">'+
      '<div class="picker">'+list+'</div></section>';
  }
  var t=state.team, rec=record(t), pg=teamPhaseGames(t), ife=ifeOf(t), ido=idoOf(t);
  var ifeR=ordinal(t,'IFE'), idoR=ordinal(t,'IDO');
  var summary=[['Jogos',rec.games],['V-E-D',rec.w+'-'+rec.d+'-'+rec.l],['Gols',rec.gf+':'+rec.ga],['Pontos',rec.pts]]
    .map(function(s){return '<div class="hcard plain"><div class="hl">'+s[0]+'</div><div class="hv">'+s[1]+'</div></div>';}).join('');

  var canRestore=pg.some(function(g){return state.excluded.has(gkey(g));});
  var matches=pg.map(function(g){ var ex=state.excluded.has(gkey(g)); var m=/^(-?\d+)-(-?\d+)/.exec(g.placar||''); var a=m?+m[1]:0,b=m?+m[2]:0; var res=a>b?'V':(a<b?'D':'E'); var col=a>b?ACC:(a<b?RED:'#a39d8e');
    return '<button class="grow '+(ex?'off':'')+'" data-act="toggleGame:'+esc(t)+'|'+g.event_id+'" title="'+(ex?'incluir':'excluir')+' este jogo">'+
      '<span class="gcheck" style="background:'+(ex?'transparent':ACC)+';border:1.5px solid '+(ex?'rgba(26,24,19,.25)':ACC)+'">'+(ex?'':'✓')+'</span>'+
      '<span class="gbadge" style="background:'+col+';opacity:'+(ex?.4:1)+'">'+res+'</span>'+
      '<span style="opacity:'+(ex?.45:1)+'">'+fimg(g.adversario,'flag')+'</span>'+
      '<span class="gmid" style="opacity:'+(ex?.45:1)+'"><span class="op">vs</span> <span class="on">'+g.adversario+'</span><br><span class="op">'+g.fase+'</span></span>'+
      '<span class="gscore" style="opacity:'+(ex?.45:1)+'">'+g.placar+'</span></button>';
  }).join('');

  var pg2=[{name:'Índices & Odds',metrics:IDX}].concat(CB);
  if(state.showAllMetrics) pg2=pg2.concat(extraGroups());
  var groupsH=pg2.map(function(g){
    var rows=g.metrics.map(function(label){ var v=valueFor(t,label); var rk=ordinal(t,label);
      var barC=lerp('#d3ccba',ACC,rk.pct), txtC=lerp('#9a9486',ACC,rk.pct);
      var vStyle= IDX.indexOf(label)>=0||label==='Gols − xG'? 'color:'+signColor(v):'';
      return '<div class="statrow"><span class="sl">'+short(label)+qm(tip(label))+'</span>'+
        '<span class="track sm"><span class="fill" style="width:'+(rk.pct*100)+'%;background:'+barC+'"></span></span>'+
        '<span class="sv" style="'+vStyle+'">'+disp(label,v)+'</span>'+
        '<span class="sr" style="color:'+txtC+'">'+(rk.rank!=null?rk.rank+'º':'–')+'</span></div>';
    }).join('');
    return '<div class="grphead2">'+g.name+'</div>'+rows;
  }).join('');

  return '<section>'+
    '<div class="phead"><div class="pid">'+fimg(t,'pflag')+'<div><div class="pname">'+t+'</div><div class="psub">Chegou até: <b>'+phaseReached(t)+'</b></div></div></div>'+
      '<button class="backbtn" data-act="clearTeam">← trocar seleção</button></div>'+
    '<div class="hero">'+
      '<div class="hcard ife" title="'+esc(tip('IFE'))+'"><div class="hl">IFE · força</div><div class="hv" style="color:'+signColor(ife)+'">'+signed(ife,2)+'</div><div class="hn">'+(ifeR.rank?ifeR.rank+'º':'–')+' entre '+ifeR.n+'</div></div>'+
      '<div class="hcard ido" title="'+esc(tip('IDO'))+'"><div class="hl">IDO · vs odds</div><div class="hv" style="color:'+signColor(ido)+'">'+signed(ido,0)+'</div><div class="hn">'+(idoR.rank?idoR.rank+'º · '+(ido>0.5?'superou o mercado':ido<-0.5?'abaixo do mercado':'na média'):'—')+'</div></div>'+
      summary+'</div>'+
    '<div class="pbody"><div>'+
      '<div style="display:flex;align-items:baseline;justify-content:space-between;margin:0 2px 8px"><span class="overline">Jogos · '+teamGames(t).length+' de '+pg.length+'</span>'+(canRestore?'<button class="linka" data-act="restoreTeam:'+esc(t)+'">restaurar</button>':'')+'</div>'+
      '<div class="psub" style="margin:0 2px 8px;font-size:11px">Toque num jogo para incluí-lo/excluí-lo — IFE, IDO e as métricas recalculam.</div>'+
      '<div class="gtoggle">'+matches+'</div></div>'+
      '<div class="mgroups"><div class="overline" style="margin:0 2px 4px">Rendimento por métrica <span style="text-transform:none;letter-spacing:0;color:var(--muted);font-weight:500">· posição entre '+ifeR.n+' seleções</span></div>'+groupsH+
      '<div style="margin:14px 0 0"><button class="custbtn '+(state.showAllMetrics?'on':'')+'" data-act="toggleAllMetrics">'+(state.showAllMetrics?'ocultar métricas extras ▴':'ver todas as métricas ▾')+'</button></div></div>'+
    '</div></section>';
}

/* ---------- eventos ---------- */
app.addEventListener('click', function(e){
  var b=e.target.closest('[data-act]'); if(!b) return;
  var a=b.dataset.act; var idx=a.indexOf(':'); var k=idx<0?a:a.slice(0,idx), v=idx<0?null:a.slice(idx+1);
  if(k==='mode'){ state.mode=v; state.metricMenuOpen=false; }
  else if(k==='phase'){ state.phase=v; }
  else if(k==='sort'){ state.sortKey=v; state.customMetric=null; }
  else if(k==='toggleMetricMenu'){ state.metricMenuOpen=!state.metricMenuOpen; state.metricQuery=''; }
  else if(k==='pickMetric'){ state.customMetric=v; state.sortKey=v; state.metricMenuOpen=false; state.metricQuery=''; }
  else if(k==='clearCustom'){ state.customMetric=null; state.sortKey='IFE'; }
  else if(k==='team'){ state.mode='team'; state.team=v; }
  else if(k==='clearTeam'){ state.team=null; state.teamQuery=''; }
  else if(k==='removeCompare'){ state.compare=state.compare.filter(function(x){return x!==v;}); }
  else if(k==='addCompare'){ if(state.compare.indexOf(v)<0&&state.compare.length<4) state.compare.push(v); state.compareQuery=''; }
  else if(k==='agg'){ state.agg=v; }
  else if(k==='toggleAllMetrics'){ state.showAllMetrics=!state.showAllMetrics; }
  else if(k==='restoreAll'){ state.excluded=new Set(); }
  else if(k==='restoreTeam'){ teamPhaseGames(v).forEach(function(g){state.excluded.delete(gkey(g));}); }
  else if(k==='toggleGame'){ var p=v.split('|'); toggleGame(p[0],+p[1]); return; }
  else return;
  render();
});
app.addEventListener('input', function(e){
  var el=e.target; if(!el.dataset||!el.dataset.act) return;
  var a=el.dataset.act;
  if(a==='q:metric'){ state.metricQuery=el.value; render(); }
  else if(a==='q:compare'){ state.compareQuery=el.value; render(); }
  else if(a==='q:team'){ state.teamQuery=el.value; render(); }
});
document.addEventListener('click', function(e){
  if(state.metricMenuOpen && !e.target.closest('.addwrap')){ state.metricMenuOpen=false; render(); }
});

/* ---------- boot ---------- */
function boot(data){
  DATA=data; FLAGS=data.flags||{}; GAMES=data.games;
  GROUPS=data.groups; PHASES=data.phases; DESC=data.descriptions||{};
  IFE_MKT=data.ifeMkt||{}; IFE_SHRINK=data.ifeShrink||4;
  TEAMS=Object.keys(GAMES.reduce(function(a,g){a[g.selecao]=1;return a;},{})).sort(function(a,b){return a.localeCompare(b,'pt-BR');});
  /* spec/régua canônicas do Python, quando presentes no payload */
  if(data.dims) DIMS=Object.keys(data.dims).map(function(n){return {name:n,comps:data.dims[n]};});
  buildIndex();
  if(data.dimsBaseline) BASE=data.dimsBaseline;
  render();
}
(function(){
  /* payload substituído começa com "{"; se ainda for o placeholder do
     template (NÃO cite o marcador aqui: o replace do Python trocaria),
     busca data/wc.json (modo dev). */
  var raw=document.getElementById('viz-data').textContent.trim();
  if(raw.charAt(0)==='{'){
    boot(JSON.parse(raw));
  } else {
    app.innerHTML='<div style="padding:60px 0"><div class="skel"></div><div class="skel"></div><div class="skel"></div><div class="skel"></div></div>';
    fetch('data/wc.json').then(function(r){return r.json();}).then(boot).catch(function(e){ app.innerHTML='<p style="padding:40px;color:#c0392b">Erro ao carregar dados: '+e+'</p>'; });
  }
})();
</script>
</body>
</html>
"""
