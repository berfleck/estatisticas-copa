#!/usr/bin/env python3
"""
sofascore_stats.py
------------------
Puxa estatísticas de TODOS os jogos da Copa do Mundo 2026 (todas as seleções,
todas as fases) direto da API interna (pública, JSON) do Sofascore, salva em
CSV e gera um dashboard HTML interativo.

Estratégia: em vez de resolver seleção por seleção, percorremos o torneio
inteiro (uniqueTournament 16 = "World Championship", temporada 2026) e, para
cada jogo finalizado, extraímos as estatísticas dos DOIS times de uma vez.

Requisitos:
    pip install curl_cffi pandas

Uso:
    python sofascore_stats.py

Saída:
    - Imprime as tabelas no terminal
    - Salva 'sofascore_stats.csv' (linha por jogo) e
      'sofascore_resumo.csv' (agregado por seleção)

Observações importantes:
    - A Sofascore bloqueia por FINGERPRINT DE TLS no edge (Varnish/Fastly):
      a lib `requests` leva 403 mesmo com User-Agent de navegador perfeito.
      Por isso usamos `curl_cffi` com impersonate="chrome", que reproduz o
      handshake TLS/HTTP2 real do Chrome. Um User-Agent no header NÃO basta.
    - Há um sleep entre chamadas para evitar rate-limit. Não remova.
    - A API é não-oficial: a estrutura pode mudar sem aviso. Se algo quebrar,
      inspecione o JSON cru e ajuste os nomes.
"""

import time
import sys
from datetime import datetime
from urllib.parse import quote

import pandas as pd
from curl_cffi import requests as cfrequests

from dashboard import build_dashboard

BASE = "https://api.sofascore.com/api/v1"

# curl_cffi já define User-Agent, sec-ch-ua, Accept etc. via impersonate.
# Aqui só complementamos com o contexto do app (a chamada vem do site).
HEADERS = {
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
}

# Sessão reaproveita conexão e mantém o mesmo fingerprint entre chamadas.
_session = cfrequests.Session(impersonate="chrome", headers=HEADERS)

# Torneio-alvo na Sofascore. A Copa do Mundo (finais) é o uniqueTournament 16,
# chamado internamente de "World Championship" (as eliminatórias são outros IDs).
# SEASON_YEAR resolve a temporada automaticamente (2026 -> seasonId 58210);
# assim o script continua válido em Copas futuras sem editar o ID na mão.
UNIQUE_TOURNAMENT_ID = 16
SEASON_YEAR = 2026
SLEEP = 0.6                         # segundos entre chamadas (78+ jogos)

# Traduz as fases do mata-mata (nome cru da API -> PT). Grupos vira "Grupos".
PHASE_PT = {
    "Round of 32": "32-avos de final",
    "Round of 16": "Oitavas de final",
    "Quarterfinals": "Quartas de final",
    "Semifinals": "Semifinais",
    "Match for 3rd place": "Disputa de 3º lugar",
    "Play off for 3rd place": "Disputa de 3º lugar",
    "Final": "Final",
}
# Ordem canônica das fases (para chips do dashboard e ordenação).
PHASE_ORDER = ["Grupos", "32-avos de final", "Oitavas de final",
               "Quartas de final", "Semifinais", "Disputa de 3º lugar", "Final"]

# Tradução dos nomes das seleções (EN -> PT). Nomes desconhecidos ficam como
# vieram (nada é perdido). Aplicada na coleta, então vale p/ CSV e dashboard.
TEAM_PT = {
    "Algeria": "Argélia", "Argentina": "Argentina", "Australia": "Austrália",
    "Austria": "Áustria", "Belgium": "Bélgica",
    "Bosnia & Herzegovina": "Bósnia e Herzegovina", "Brazil": "Brasil",
    "Cabo Verde": "Cabo Verde", "Canada": "Canadá", "Colombia": "Colômbia",
    "Croatia": "Croácia", "Curaçao": "Curaçao", "Czechia": "Tchéquia",
    "Côte d'Ivoire": "Costa do Marfim", "DR Congo": "RD Congo",
    "Ecuador": "Equador", "Egypt": "Egito", "England": "Inglaterra",
    "France": "França", "Germany": "Alemanha", "Ghana": "Gana", "Haiti": "Haiti",
    "Iran": "Irã", "Iraq": "Iraque", "Japan": "Japão", "Jordan": "Jordânia",
    "Mexico": "México", "Morocco": "Marrocos", "Netherlands": "Países Baixos",
    "New Zealand": "Nova Zelândia", "Norway": "Noruega", "Panama": "Panamá",
    "Paraguay": "Paraguai", "Portugal": "Portugal", "Qatar": "Catar",
    "Saudi Arabia": "Arábia Saudita", "Scotland": "Escócia", "Senegal": "Senegal",
    "South Africa": "África do Sul", "South Korea": "Coreia do Sul",
    "Spain": "Espanha", "Sweden": "Suécia", "Switzerland": "Suíça",
    "Tunisia": "Tunísia", "Türkiye": "Turquia", "USA": "Estados Unidos",
    "Uruguay": "Uruguai", "Uzbekistan": "Uzbequistão",
}


def pt_team(name):
    """Nome da seleção em PT (ou o original, se não houver tradução)."""
    return TEAM_PT.get(name, name)


# ---------------------------------------------------------------------------
# Camada de rede
# ---------------------------------------------------------------------------
def sofa_get(path, retries=3):
    """GET num endpoint da API do Sofascore, com retry e sleep educado."""
    url = f"{BASE}/{path.lstrip('/')}"
    for attempt in range(1, retries + 1):
        try:
            resp = _session.get(url, timeout=15)
            if resp.status_code == 200:
                time.sleep(SLEEP)
                return resp.json()
            if resp.status_code == 404:
                # Ex.: jogo sem estatísticas disponíveis.
                return None
            print(f"  [aviso] HTTP {resp.status_code} em {url} "
                  f"(tentativa {attempt}/{retries})")
        except cfrequests.RequestsError as e:
            print(f"  [aviso] erro de rede em {url}: {e} "
                  f"(tentativa {attempt}/{retries})")
        time.sleep(SLEEP * attempt)  # backoff simples
    return None


# ---------------------------------------------------------------------------
# Resolução de torneio / temporada e listagem de jogos
# ---------------------------------------------------------------------------
def resolve_season_id(ut_id, year):
    """Descobre o seasonId da temporada `year` no uniqueTournament `ut_id`."""
    data = sofa_get(f"unique-tournament/{ut_id}/seasons")
    if not data:
        return None
    for se in data.get("seasons", []):
        if se.get("year") == year or str(se.get("year")) == str(year):
            return se.get("id")
    return None


def _phase_label(name):
    """Nome cru da rodada -> fase em PT (sem nome = fase de grupos)."""
    return PHASE_PT.get(name, name) if name else "Grupos"


def get_season_events(ut_id, season_id):
    """
    Retorna TODOS os jogos FINALIZADOS (status 100) da temporada, varrendo
    RODADA A RODADA (endpoint /events/round/...). Usamos as rodadas — e não o
    feed /events/last — porque este último às vezes omite jogos (a Copa 2026
    perdia England x Croatia da 1ª rodada). Cada evento é carimbado com a fase.
    """
    meta = sofa_get(f"unique-tournament/{ut_id}/season/{season_id}/rounds")
    rounds = (meta or {}).get("rounds") or [{"round": 1}, {"round": 2}, {"round": 3}]

    events = {}
    for rd in rounds:
        rnum, slug, name = rd.get("round"), rd.get("slug"), rd.get("name")
        path = f"unique-tournament/{ut_id}/season/{season_id}/events/round/{rnum}"
        if slug:                       # mata-mata exige o slug (senão 404)
            path += f"/slug/{slug}"
        data = sofa_get(path)
        if not data:
            continue
        for ev in data.get("events", []):
            if ev.get("status", {}).get("code") == 100:   # Ended
                ev["_fase"] = _phase_label(name)
                events[ev["id"]] = ev                     # dedupe por id
    out = list(events.values())
    out.sort(key=lambda e: e.get("startTimestamp", 0))
    return out


# ---------------------------------------------------------------------------
# Extração de estatísticas
# ---------------------------------------------------------------------------
# Rótulos das colunas de identificação (para exibir/salvar em português).
ID_LABELS = {
    "selecao": "Seleção",
    "adversario": "Adversário",
    "placar": "Placar",
    "fase": "Fase",
    "event_id": "ID do Jogo",
}

# Tradução EN -> PT de TODAS as estatísticas de time que a API entrega.
# A ordem aqui define a ordem das colunas no CSV detalhado.
# Duplicatas propositais (ex.: "Tackles" e "Total tackles") apontam para o
# mesmo rótulo para colapsarem numa única coluna.
# Valores em "x/y (z%)" viram o 1º número (a contagem de acertos) — por isso
# alguns rótulos dizem "(certos)" / "(ganhos)".
STAT_LABELS = {
    # Visão geral
    "Ball possession": "Posse de Bola (%)",
    "Expected goals": "xG (Gols Esperados)",
    "Total shots": "Finalizações",
    "Big chances": "Grandes Chances",
    "Goalkeeper saves": "Defesas do Goleiro",
    "Total saves": "Defesas do Goleiro",
    "Corner kicks": "Escanteios",
    "Fouls": "Faltas",
    "Free kicks": "Cobranças de Falta",
    "Yellow cards": "Cartões Amarelos",
    "Red cards": "Cartões Vermelhos",
    "Passes": "Passes",
    "Distance covered": "Distância Percorrida (km)",
    "Number of sprints": "Sprints",
    # Chutes
    "Shots on target": "Chutes no Alvo",
    "Shots off target": "Chutes para Fora",
    "Blocked shots": "Chutes Bloqueados",
    "Hit woodwork": "Bolas na Trave",
    "Shots inside box": "Chutes Dentro da Área",
    "Shots outside box": "Chutes Fora da Área",
    # Ataque
    "Big chances scored": "Grandes Chances Convertidas",
    "Big chances missed": "Grandes Chances Perdidas",
    "Touches in penalty area": "Toques na Área",
    "Through balls": "Passes em Profundidade",
    "Fouled in final third": "Faltas Sofridas no Último Terço",
    "Offsides": "Impedimentos",
    # Passes
    "Accurate passes": "Passes Certos",
    "Throw-ins": "Arremessos Laterais",
    "Final third entries": "Entradas no Último Terço",
    "Final third phase": "Ações no Último Terço",
    "Long balls": "Bolas Longas (certas)",
    "Crosses": "Cruzamentos (certos)",
    # Duelos
    "Duels": "Duelos Ganhos (%)",
    "Dispossessed": "Perdas de Bola",
    "Ground duels": "Duelos no Chão (ganhos)",
    "Aerial duels": "Duelos Aéreos (ganhos)",
    "Dribbles": "Dribles (certos)",
    # Defesa
    "Tackles": "Desarmes",
    "Total tackles": "Desarmes",
    "Tackles won": "Desarmes Ganhos (%)",
    "Interceptions": "Interceptações",
    "Recoveries": "Recuperações de Bola",
    "Clearances": "Cortes",
    "Errors lead to a shot": "Erros que Levaram a Finalização",
    "Errors lead to a goal": "Erros que Levaram a Gol",
    # Goleiro
    "Goals prevented": "Gols Evitados",
    "High claims": "Saídas Aéreas do Goleiro",
    "Big saves": "Defesas Difíceis",
    "Penalty saves": "Defesas de Pênalti",
    "Punches": "Socos do Goleiro",
    "Goal kicks": "Tiros de Meta",
}

# Colunas (rótulos em PT) que entram no resumo agregado. Mantém o resumo
# enxuto mesmo com o detalhado tendo tudo. Percentuais (rótulo com "(%)")
# são agregados por MÉDIA; o resto por SOMA.
SUMMARY_COLS = [
    "Posse de Bola (%)",
    "xG (Gols Esperados)",
    "Finalizações",
    "Chutes no Alvo",
    "Grandes Chances",
    "Grandes Chances Convertidas",
    "Toques na Área",
    "Passes",
    "Passes Certos",
    "Duelos Ganhos (%)",
    "Desarmes",
    "Interceptações",
    "Recuperações de Bola",
    "Gols Evitados",
    "Escanteios",
    "Faltas",
    "Impedimentos",
]

# Agrupamento das estatísticas (rótulos PT) por seção — usado no dashboard
# para organizar/filtrar as métricas por categoria.
STAT_GROUPS = {
    "Visão geral": [
        "Posse de Bola (%)", "xG (Gols Esperados)", "Finalizações",
        "Grandes Chances", "Defesas do Goleiro", "Escanteios", "Faltas",
        "Cobranças de Falta", "Cartões Amarelos", "Cartões Vermelhos", "Passes",
        "Distância Percorrida (km)", "Sprints",
    ],
    "Chutes": [
        "Chutes no Alvo", "Chutes para Fora", "Chutes Bloqueados",
        "Bolas na Trave", "Chutes Dentro da Área", "Chutes Fora da Área",
    ],
    "Ataque": [
        "Grandes Chances Convertidas", "Grandes Chances Perdidas",
        "Toques na Área", "Passes em Profundidade",
        "Faltas Sofridas no Último Terço", "Impedimentos",
    ],
    "Passes": [
        "Passes Certos", "Arremessos Laterais", "Entradas no Último Terço",
        "Ações no Último Terço", "Bolas Longas (certas)", "Cruzamentos (certos)",
    ],
    "Duelos": [
        "Duelos Ganhos (%)", "Perdas de Bola", "Duelos no Chão (ganhos)",
        "Duelos Aéreos (ganhos)", "Dribles (certos)",
    ],
    "Defesa": [
        "Desarmes", "Desarmes Ganhos (%)", "Interceptações",
        "Recuperações de Bola", "Cortes", "Erros que Levaram a Finalização",
        "Erros que Levaram a Gol",
    ],
    "Goleiro": [
        "Gols Evitados", "Saídas Aéreas do Goleiro", "Defesas Difíceis",
        "Defesas de Pênalti", "Socos do Goleiro", "Tiros de Meta",
    ],
}


def parse_statistics(stats_json, home_name, away_name, target_team):
    """
    Extrai TODAS as estatísticas do período ALL (jogo inteiro) para o time
    alvo. Retorna um dict achatado {rótulo_PT: valor}. Estatísticas sem
    tradução conhecida entram com o nome original em inglês (nada é perdido).
    """
    if not stats_json:
        return {}
    all_period = None
    for block in stats_json.get("statistics", []):
        if block.get("period") == "ALL":
            all_period = block
            break
    if all_period is None:
        return {}

    is_home = target_team.lower() == home_name.lower()
    side = "home" if is_home else "away"

    out = {}
    for group in all_period.get("groups", []):
        for item in group.get("statisticsItems", []):
            name = item.get("name")
            label = STAT_LABELS.get(name, name)  # fallback: nome em inglês
            # A API já entrega valores separados para home/away.
            out[label] = _clean(item.get(side))
    return out


def _clean(v):
    """Normaliza valores: '65%' -> 65.0, '12 (450)' -> 12, '1.85' -> 1.85."""
    if v is None:
        return None
    s = str(v).strip().replace("%", "")
    if not s:
        return None
    # casos tipo "450/500 (90%)" ou "12 (7)": pega o primeiro número
    token = s.split()[0].split("/")[0]
    try:
        return float(token) if "." in token else int(token)
    except ValueError:
        return v


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def collect_tournament(ut_id, season_id):
    """
    Percorre TODOS os jogos finalizados da temporada e devolve uma linha por
    (jogo x time) — cada partida gera 2 linhas (mandante e visitante), com uma
    única chamada ao endpoint de estatísticas.
    """
    events = get_season_events(ut_id, season_id)
    if not events:
        print("  [erro] nenhum jogo finalizado encontrado no torneio")
        return []
    print(f"  {len(events)} jogos finalizados. Puxando estatísticas...")

    rows = []
    for i, ev in enumerate(events, 1):
        eid = ev["id"]
        home = pt_team(ev["homeTeam"]["name"])
        away = pt_team(ev["awayTeam"]["name"])
        hg = ev.get("homeScore", {}).get("current")
        ag = ev.get("awayScore", {}).get("current")
        fase = ev.get("_fase", "Grupos")

        print(f"  [{i}/{len(events)}] {home} {hg}-{ag} {away} ({fase})")
        stats_json = sofa_get(f"event/{eid}/statistics")

        # uma linha para cada lado da partida
        for team, opp, gf, ga in ((home, away, hg, ag), (away, home, ag, hg)):
            row = {"selecao": team, "adversario": opp,
                   "placar": f"{gf}-{ga}", "fase": fase, "event_id": eid}
            row.update(parse_statistics(stats_json, home, away, team))
            rows.append(row)
    return rows


def main():
    season_id = resolve_season_id(UNIQUE_TOURNAMENT_ID, SEASON_YEAR)
    if not season_id:
        print(f"[erro] não achei a temporada {SEASON_YEAR} do torneio "
              f"{UNIQUE_TOURNAMENT_ID}.")
        sys.exit(1)
    print(f"== Copa {SEASON_YEAR} (torneio {UNIQUE_TOURNAMENT_ID}, "
          f"temporada {season_id}) ==")

    all_rows = collect_tournament(UNIQUE_TOURNAMENT_ID, season_id)
    if not all_rows:
        print("\nNada coletado. Verifique conexão / fingerprint / IDs.")
        sys.exit(1)

    df = pd.DataFrame(all_rows)

    # ordena colunas: identificação, depois métricas na ordem de STAT_LABELS.
    # Estatísticas sem tradução (nome em inglês) vão para o fim, nada some.
    id_cols = ["selecao", "adversario", "placar", "fase", "event_id"]
    metric_order = [lbl for lbl in dict.fromkeys(STAT_LABELS.values())
                    if lbl in df.columns]
    extras = [c for c in df.columns
              if c not in id_cols and c not in metric_order]
    df = df[id_cols + metric_order + extras]

    # ---- CSV detalhado: TODAS as estatísticas de time, 1 linha por jogo ----
    df_out = df.rename(columns=ID_LABELS)
    n_stats = len(metric_order + extras)
    n_teams = df["selecao"].nunique()
    n_games = df["event_id"].nunique()
    print(f"\n===== COLETADO: {n_games} jogos, {n_teams} seleções, "
          f"{len(df)} linhas, {n_stats} estatísticas =====")
    df_out.to_csv("sofascore_stats.csv", index=False, encoding="utf-8-sig")

    # ---- CSV resumo: agregado por seleção (subconjunto curado) ----
    # percentuais (rótulo com "(%)") viram MÉDIA; contagens viram SOMA.
    summary_cols = [c for c in SUMMARY_COLS if c in df.columns]
    agg_map = {c: ("mean" if "(%)" in c else "sum") for c in summary_cols}
    agg = (df.groupby("selecao")[summary_cols].agg(agg_map)
             .round(2).rename_axis(ID_LABELS["selecao"]))
    agg.to_csv("sofascore_resumo.csv", encoding="utf-8-sig")

    # ---- Dashboard HTML interativo (offline) ----
    all_metrics = metric_order + extras
    groups = [{"name": g, "stats": [s for s in cols if s in df.columns]}
              for g, cols in STAT_GROUPS.items()
              if any(s in df.columns for s in cols)]
    used = {s for g in groups for s in g["stats"]}
    outras = [m for m in all_metrics if m not in used]
    if outras:
        groups.append({"name": "Outras", "stats": outras})

    games = []
    for _, r in df.iterrows():
        games.append({
            "selecao": r["selecao"],
            "adversario": r["adversario"],
            "placar": r["placar"],
            "fase": r["fase"],
            "event_id": int(r["event_id"]),
            "values": {m: _json_num(r[m]) for m in all_metrics},
        })
    phases = [p for p in PHASE_ORDER if p in set(df["fase"])]
    build_dashboard(games, groups, "dashboard.html",
                    phases=phases,
                    generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"))

    print("\nArquivos salvos: sofascore_stats.csv, sofascore_resumo.csv "
          "e dashboard.html")
    print("Abra o dashboard.html no navegador para explorar/filtrar/comparar.")


def _json_num(v):
    """Valor -> tipo nativo p/ JSON (NaN vira None)."""
    if v is None:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and v != v:   # NaN
        return None
    return v


if __name__ == "__main__":
    main()
