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
    python sofascore_stats.py            # incremental: só puxa jogos novos
    python sofascore_stats.py --full     # ignora o cache e re-puxa TUDO

Coleta incremental:
    As estatísticas de um jogo já finalizado não mudam mais. Por isso, ao rodar,
    o script lê o 'sofascore_stats.csv' existente e PULA os jogos que já têm
    estatísticas — chamando o endpoint de estatísticas (a parte cara/lenta) só
    para os jogos novos. Jogos gravados sem estatísticas (ex.: stats ainda
    indisponíveis numa rodada anterior) são re-tentados. Use --full para forçar
    uma releitura completa (ex.: se a estrutura da API mudar).

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

import os
import time
import sys
from datetime import datetime
from fractions import Fraction
from urllib.parse import quote

import numpy as np
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

# Arquivos de saída (o detalhado também serve de cache p/ coleta incremental).
STATS_CSV = "sofascore_stats.csv"
RESUMO_CSV = "sofascore_resumo.csv"

# Traduz as fases do mata-mata (nome cru da API -> PT). Grupos vira "Grupos".
# A fração segue o nº de CONFRONTOS (oitavas = 16 equipes/8 jogos), então o
# "Round of 32" (32 equipes/16 jogos) é 1/16 da final: 16-avos de final.
PHASE_PT = {
    "Round of 32": "16-avos de final",
    "Round of 16": "Oitavas de final",
    "Quarterfinals": "Quartas de final",
    "Semifinals": "Semifinais",
    "Match for 3rd place": "Disputa de 3º lugar",
    "Play off for 3rd place": "Disputa de 3º lugar",
    "Final": "Final",
}
# Ordem canônica das fases (para chips do dashboard e ordenação).
PHASE_ORDER = ["Grupos", "16-avos de final", "Oitavas de final",
               "Quartas de final", "Semifinais", "Disputa de 3º lugar", "Final"]

# Rótulos de fase antigos -> atuais. A fase fica CARIMBADA no CSV de cache na
# coleta, então renomear em PHASE_PT não basta: load_existing() aplica este
# mapa para corrigir caches gravados com o nome antigo.
PHASE_LEGACY = {"32-avos de final": "16-avos de final"}

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
    Retorna TODOS os jogos FINALIZADOS da temporada, varrendo RODADA A RODADA
    (endpoint /events/round/...). Usamos as rodadas — e não o feed /events/last
    — porque este último às vezes omite jogos (a Copa 2026 perdia England x
    Croatia da 1ª rodada). Cada evento é carimbado com a fase.

    "Finalizado" = status.type == "finished", o que cobre o fim no tempo normal
    (code 100, "Ended"), na PRORROGAÇÃO (110, "AET") e nos PÊNALTIS (120, "AP").
    Filtrar só por code == 100 perdia os jogos de mata-mata decididos no extra
    (ex.: Netherlands 3-4 Morocco nos pênaltis ficava de fora).
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
            if ev.get("status", {}).get("type") == "finished":  # 100/110/120
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

# Métricas dos índices (derivadas; não vêm da API de estatísticas).
# "P(Vitória %)" é coletada das odds de abertura e CACHEADA no CSV; "IDO" e
# "xGD" são recalculados em compute_performance_index() e "IFE" em
# compute_strength_index() a cada execução. A ordem aqui é a de exibição
# (índices primeiro). Percentuais e estas métricas são agregados por MÉDIA no
# resumo (ver main()).
INDEX_LABELS = ["IDO", "IFE", "P(Vitória %)", "xGD"]

# Colunas DERIVADAS que são recalculadas toda execução — descartadas ao carregar
# o CSV para nunca ficarem defasadas (P(Vitória %) NÃO entra: é dado de cache).
# "Índice" é o nome legado do IDO, mantido só para limpar CSVs antigos.
COMPUTED_COLS = ["IDO", "IFE", "xGD", "xG Concedido",
                 "Grandes Chances Concedidas",
                 "Gols", "Gols Sofridos", "Gols − xG", "Índice"]

# Encolhimento do ajuste de desempenho do IFE: com n jogos considerados, o
# resíduo médio entra com peso n/(n+IFE_SHRINK) — assim poucos jogos de
# sorte/azar não movem demais o rating. Usado no cálculo estático (CSVs) e no
# dinâmico do dashboard (jogos selecionados), que precisam bater.
IFE_SHRINK = 4.0

# Colunas (rótulos em PT) que entram no resumo agregado. Mantém o resumo
# enxuto mesmo com o detalhado tendo tudo. Percentuais (rótulo com "(%)") e as
# métricas do índice são agregados por MÉDIA; o resto por SOMA.
SUMMARY_COLS = INDEX_LABELS + [
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
    "Índices & Odds": [
        "IDO", "IFE", "P(Vitória %)", "xGD",
    ],
    "Eficiência": [
        "Gols", "Gols Sofridos", "Gols − xG",
        "Grandes Chances Convertidas", "Grandes Chances Perdidas",
    ],
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
        "xG Concedido", "Grandes Chances Concedidas",
        "Desarmes", "Desarmes Ganhos (%)", "Interceptações",
        "Recuperações de Bola", "Cortes", "Erros que Levaram a Finalização",
        "Erros que Levaram a Gol",
    ],
    "Goleiro": [
        "Gols Evitados", "Saídas Aéreas do Goleiro", "Defesas Difíceis",
        "Defesas de Pênalti", "Socos do Goleiro", "Tiros de Meta",
    ],
}

# As 5 dimensões compostas do dashboard (radar/escores 0-100). Formato:
# {nome: [(métrica, peso) | (métrica, peso, inverter)]}. Chaves com "@" são
# derivadas por team-jogo (ver _DERIVADAS); "inverter" = quanto menor, melhor.
# O escore no dashboard é a média ponderada dos z-scores dos componentes
# (régua global de baseline_dimensoes), mapeada por 50 + 15*z para 0-100.
# Calibração: os pesos aqui e o fator 15 no front (dimScore) são os únicos
# pontos de sintonia.
DIMENSOES = {
    "Ataque": [
        ("xG (Gols Esperados)", .40), ("Grandes Chances", .25),
        ("Chutes no Alvo", .20), ("Finalizações", .15),
    ],
    "Finalização": [
        ("Gols − xG", .40), ("@xg_por_fin", .30),
        ("Grandes Chances Convertidas", .30),
    ],
    "Posse": [
        ("Posse de Bola (%)", .35), ("Passes Certos", .30),
        ("Entradas no Último Terço", .35),
    ],
    "Pressão": [
        ("Toques na Área", .40), ("Ações no Último Terço", .30),
        ("Faltas Sofridas no Último Terço", .30),
    ],
    "Defesa": [
        ("xG Concedido", .45, True), ("Grandes Chances Concedidas", .30, True),
        ("Gols Evitados", .15), ("Duelos Ganhos (%)", .10),
    ],
}

# Componentes derivados por team-jogo (não são colunas do CSV). O front
# calcula os mesmos valores por jogo com estas chaves.
_DERIVADAS = {
    "@xg_por_fin": lambda d: d["xG (Gols Esperados)"]
    / d["Finalizações"].where(d["Finalizações"] > 0),
}


def _valor_componente(df, key):
    """Série (por team-jogo) de um componente de dimensão; NaN onde faltar."""
    if key in _DERIVADAS:
        try:
            return _DERIVADAS[key](df)
        except KeyError:
            return pd.Series(dtype=float)
    if key not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[key], errors="coerce")


def baseline_dimensoes(df):
    """
    Régua global das dimensões: média e desvio-padrão de cada componente
    sobre TODOS os team-jogos da base. Vai no payload como "dimsBaseline" —
    o dashboard usa esta régua (fixa) para os z-scores, de modo que filtrar
    jogos muda o escore da seleção, não a régua. Componentes sem dados ficam
    de fora (o front ignora componentes sem baseline).
    """
    out = {}
    comps = {c for spec in DIMENSOES.values() for (c, *_) in spec}
    for c in sorted(comps):
        s = _valor_componente(df, c).dropna()
        if s.empty:
            continue
        sd = float(s.std())
        if sd != sd or sd == 0:          # NaN (n<2) ou constante
            sd = 1.0
        out[c] = {"mean": round(float(s.mean()), 4), "sd": round(sd, 4)}
    return out


# Descrições curtas (viram tooltip no dashboard) das métricas menos óbvias.
# Métricas fora deste dict simplesmente não têm tooltip. NÃO use aspas duplas
# nos textos (eles entram no atributo title=... do HTML).
STAT_DESCRIPTIONS = {
    "IDO": ("Índice de Desempenho vs Odds: quanto o time superou (positivo) ou "
            "ficou abaixo (negativo) do desempenho que as odds pré-jogo previam. "
            "0 = rendeu exatamente como o mercado esperava. Mede surpresa, não "
            "força: para comparar o nível entre seleções, veja o IFE."),
    "IFE": ("Índice de Força da Equipe: força estimada da seleção numa régua "
            "única. Parte do rating implícito nas odds de TODOS os jogos da "
            "Copa (corrige o calendário: quem caiu em grupo forte não é "
            "punido) e incorpora o rendimento dos jogos selecionados — filtre "
            "fases ou jogos para ver a força naquele recorte; quanto mais "
            "jogos, mais o rendimento pesa. Unidade: saldo de xG esperado por "
            "jogo contra um adversário médio da Copa; a diferença de IFE entre "
            "duas seleções estima o xGD de um confronto hipotético entre elas, "
            "mesmo que nunca tenham se enfrentado."),
    "P(Vitória %)": ("Probabilidade de vitória pré-jogo, calculada das odds de "
                     "abertura (1X2, já sem a margem da banca). Baixo = era "
                     "azarão; alto = era favorito."),
    "xGD": ("Saldo de gols esperados no jogo: xG a favor menos xG contra. "
            "Positivo = criou chances melhores que as do adversário."),
    "Gols": ("Gols marcados no jogo (tempo normal e prorrogação; disputa de "
             "pênaltis não conta)."),
    "Gols Sofridos": ("Gols sofridos no jogo (tempo normal e prorrogação; "
                      "disputa de pênaltis não conta)."),
    "Gols − xG": ("Conversão: gols marcados menos gols esperados (xG). Muito "
                  "positivo = o time marcou acima da qualidade das chances — "
                  "placares recentes inflados, tende a regredir à média; "
                  "negativo = desperdiçou chances e tende a melhorar."),
    "xG (Gols Esperados)": ("Gols esperados: soma da probabilidade de gol de cada "
                            "finalização. Mede a qualidade das chances criadas, "
                            "não o placar."),
    "Grandes Chances": ("Oportunidades claras de gol — situações em que se espera "
                        "que o atacante marque."),
    "xG Concedido": ("Gols esperados criados pelo ADVERSÁRIO no jogo — mede a "
                     "qualidade das chances que a defesa cedeu."),
    "Grandes Chances Concedidas": "Oportunidades claras de gol cedidas ao adversário.",
    "Duelos Ganhos (%)": "Percentual de disputas de bola (no chão e aéreas) vencidas.",
    "Gols Evitados": ("Gols que o goleiro evitou além do esperado para aqueles "
                      "chutes — mede a qualidade das defesas."),
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
def load_existing(path):
    """
    Carrega o CSV detalhado já existente (se houver) e devolve
    (dataframe_interno, ids_ja_coletados).

    `ids_ja_coletados` são os jogos que JÁ têm estatísticas — a coleta pula
    esses (o placar/estatísticas de um jogo finalizado não muda mais). Jogos
    gravados SEM estatísticas ficam de fora do conjunto e são puxados de novo.
    O dataframe volta com as colunas de identificação nos nomes internos
    (selecao, adversario, ...), pronto para juntar com as linhas novas.
    """
    if not os.path.exists(path):
        return None, set()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception as e:                       # CSV corrompido/incompatível
        print(f"  [aviso] não consegui ler {path} ({e}); refazendo do zero.")
        return None, set()

    # Desfaz o rename de exibição (Seleção -> selecao etc.) p/ bater com as
    # linhas coletadas. Rótulos das estatísticas já estão em PT nos dois lados.
    df = df.rename(columns={v: k for k, v in ID_LABELS.items()})
    if "event_id" not in df.columns or df.empty:
        return None, set()
    df["event_id"] = df["event_id"].astype(int)

    # Colunas derivadas são recalculadas em main(); descarta versões antigas do
    # CSV para não deixarem fantasmas (ex.: coluna "Índice" após virar "IDO").
    df = df.drop(columns=[c for c in COMPUTED_COLS if c in df.columns])

    # Corrige rótulos de fase antigos gravados no cache (ex.: "32-avos de
    # final" -> "16-avos de final").
    if "fase" in df.columns:
        df["fase"] = df["fase"].replace(PHASE_LEGACY)

    id_cols = ["selecao", "adversario", "placar", "fase", "event_id"]
    stat_cols = [c for c in df.columns if c not in id_cols]
    if stat_cols:
        has_stats = df[stat_cols].notna().any(axis=1)
        done = set(df.loc[has_stats, "event_id"])
    else:
        done = set()
    return df, done


def pregame_win_probs(eid):
    """
    Probabilidades de vitória PRÉ-JOGO (p_mandante, p_visitante) a partir das
    odds de ABERTURA (initialFractionalValue) do mercado 1X2, já SEM a margem
    da banca (normalizadas com o empate para somar 1). Retorna (None, None) se
    o jogo não tiver odds 1X2.

    Odd fracionária -> decimal: 3/4 vira 1.75. Prob implícita = 1/decimal; a
    soma das três (1/X/2) passa de 1 por causa da margem, então dividimos pela
    soma para remover a margem. Usamos a abertura porque reflete o mercado
    ANTES do dinheiro de última hora — o "favoritismo pré-jogo" que queremos.
    """
    data = sofa_get(f"event/{eid}/odds/1/all")
    if not data:
        return None, None
    ft = next((m for m in data.get("markets", [])
               if m.get("marketName") == "Full time"
               and m.get("marketGroup") == "1X2"), None)
    if not ft:
        return None, None
    dec = {}
    for c in ft.get("choices", []):
        frac = c.get("initialFractionalValue") or c.get("fractionalValue")
        try:
            dec[c["name"]] = float(Fraction(frac)) + 1.0
        except (TypeError, ValueError, ZeroDivisionError):
            return None, None
    if not {"1", "2"} <= set(dec):     # precisa ao menos de mandante/visitante
        return None, None
    inv = {k: 1.0 / v for k, v in dec.items()}
    tot = sum(inv.values())
    return inv["1"] / tot, inv["2"] / tot


def _disp(score):
    """Placar de EXIBIÇÃO do lado (campo 'display' da API): resultado real da
    partida — inclui gols da prorrogação, mas NÃO a disputa de pênaltis.
    Cai para 'current' só se 'display' faltar. Nunca use 'current' direto: em
    jogos de pênaltis ele soma a disputa (ex.: 1-1 vira 3-4)."""
    v = score.get("display")
    return v if v is not None else score.get("current")


def _placar(gf, ga, pf, pa):
    """'gf-ga', anexando '(pên pf-pa)' quando houve disputa de pênaltis."""
    s = f"{gf}-{ga}"
    if pf is not None and pa is not None:
        s += f" (pên {pf}-{pa})"
    return s


def collect_tournament(ut_id, season_id, known_ids=frozenset()):
    """
    Percorre os jogos finalizados da temporada e devolve uma linha por
    (jogo x time) — cada partida gera 2 linhas (mandante e visitante), com uma
    única chamada ao endpoint de estatísticas.

    `known_ids`: ids de jogos que já têm estatísticas coletadas. Esses são
    pulados (não geram chamada ao endpoint de estatísticas), então só os jogos
    novos são efetivamente puxados.
    """
    events = get_season_events(ut_id, season_id)
    if not events:
        print("  [erro] nenhum jogo finalizado encontrado no torneio")
        return []

    pending = [ev for ev in events if ev["id"] not in known_ids]
    cached = len(events) - len(pending)
    if cached:
        print(f"  {len(events)} jogos finalizados — {cached} já em cache, "
              f"{len(pending)} novo(s) para puxar.")
    else:
        print(f"  {len(events)} jogos finalizados. Puxando estatísticas...")
    if not pending:
        return []

    rows = []
    for i, ev in enumerate(pending, 1):
        eid = ev["id"]
        home = pt_team(ev["homeTeam"]["name"])
        away = pt_team(ev["awayTeam"]["name"])
        hs, as_ = ev.get("homeScore", {}), ev.get("awayScore", {})
        hg, ag = _disp(hs), _disp(as_)               # resultado real (sem pênaltis)
        hp, ap = hs.get("penalties"), as_.get("penalties")
        fase = ev.get("_fase", "Grupos")
        # Favoritismo pré-jogo (odds de abertura), por lado. Cacheado no CSV
        # junto das estatísticas, então só puxamos para os jogos novos.
        p_home, p_away = pregame_win_probs(eid)

        print(f"  [{i}/{len(pending)}] {home} {hg}-{ag} {away} ({fase})")
        stats_json = sofa_get(f"event/{eid}/statistics")

        # uma linha para cada lado da partida
        for team, opp, gf, ga, pf, pa, pv in ((home, away, hg, ag, hp, ap, p_home),
                                              (away, home, ag, hg, ap, hp, p_away)):
            row = {"selecao": team, "adversario": opp,
                   "placar": _placar(gf, ga, pf, pa), "fase": fase, "event_id": eid,
                   "P(Vitória %)": round(pv * 100, 1) if pv is not None else None}
            row.update(parse_statistics(stats_json, home, away, team))
            rows.append(row)
    return rows


def compute_performance_index(df):
    """
    Adiciona ao dataframe as colunas derivadas do IDO (Índice de Desempenho vs
    Odds):

      - "xGD" : xG do time menos o xG do adversário no jogo (saldo de xG).
      - "IDO" : quanto o time superou o xGD que as odds pré-jogo previam, numa
                escala CENTRADA em zero (~ −100 a +100). 0 = exatamente o
                previsto pelo mercado; positivo = rendeu acima do esperado;
                negativo = abaixo.

    Método: ajusta, sobre TODOS os jogos, o xGD esperado em função do
    favoritismo pré-jogo (regressão linear xGD ~ P(vitória)); o IDO é o resíduo
    (real − esperado) padronizado. Assim um azarão que joga de igual para igual
    pontua alto, e um favorito só sobe se superar a expectativa. Recalculado a
    cada execução, então o modelo se refina conforme entram jogos.

    Jogos sem xG ou sem odds ficam com IDO vazio (NaN) — não atrapalham o
    ajuste (são excluídos) nem quebram o dashboard.

    Ao final chama compute_strength_index(), que reaproveita a mesma reta de
    expectativa e os resíduos para derivar o "IFE" (rating por seleção).
    """
    xg = "xG (Gols Esperados)"
    if xg not in df.columns or "P(Vitória %)" not in df.columns:
        return df                       # sem insumos, nada a calcular

    # Cada jogo tem 2 linhas (os dois lados); o xG do adversário é
    # (soma do xG do jogo) − (xG do próprio time). Se faltar o xG de algum
    # lado (n_xg < 2), o saldo fica indefinido (NaN) para não inventar 0.
    grp = df.groupby("event_id")[xg]
    total_xg, n_xg = grp.transform("sum"), grp.transform("count")
    df["xGD"] = (df[xg] - (total_xg - df[xg])).round(2)
    df.loc[n_xg < 2, "xGD"] = np.nan

    # Métricas "sofridas" = produção do ADVERSÁRIO no mesmo jogo. Entram na
    # dimensão Defesa e ficam canônicas nos CSVs (grupo "Defesa" no dashboard).
    df["xG Concedido"] = (total_xg - df[xg]).round(2)
    df.loc[n_xg < 2, "xG Concedido"] = np.nan
    bc = "Grandes Chances"
    if bc in df.columns:
        grp_bc = df.groupby("event_id")[bc]
        df["Grandes Chances Concedidas"] = grp_bc.transform("sum") - df[bc]
        df.loc[grp_bc.transform("count") < 2, "Grandes Chances Concedidas"] = np.nan

    # Gols do placar (tempo normal + prorrogação; a disputa de pênaltis fica
    # de fora — mesmo critério do placar exibido). "Gols − xG" é a conversão:
    # quanto o time marcou acima/abaixo da qualidade das chances que criou.
    gols = df["placar"].astype(str).str.extract(r"^(-?\d+)-(-?\d+)")
    df["Gols"] = pd.to_numeric(gols[0], errors="coerce")
    df["Gols Sofridos"] = pd.to_numeric(gols[1], errors="coerce")
    df["Gols − xG"] = (df["Gols"] - df[xg]).round(2)

    prob = pd.to_numeric(df["P(Vitória %)"], errors="coerce") / 100.0
    ok = df["xGD"].notna() & prob.notna()
    if ok.sum() >= 5:
        b1, b0 = np.polyfit(prob[ok], df.loc[ok, "xGD"], 1)   # xGD_esp = b0 + b1*P
        resid = df["xGD"] - (b0 + b1 * prob)
        sd = resid[ok].std()
        if sd and sd == sd:             # sd não-nulo e não-NaN
            # Escala centrada: ~±30 por desvio-padrão de superação; ±100 mapeia
            # o teto de ~3,3 desvios (extremos). 0 = jogou como as odds previam.
            df["IDO"] = (30 * (resid / sd)).clip(-100, 100).round(1)
            print(f"  IDO: xGD_esperado = {b0:+.2f} {b1:+.2f}*P(vit) "
                  f"(ajustado em {int(ok.sum())} team-jogos)")
        # IFE reaproveita a mesma reta de expectativa e os mesmos resíduos.
        df = compute_strength_index(df, b0 + b1 * prob, resid, ok)
    return df


def compute_strength_index(df, xgd_esp, resid, ok):
    """
    Adiciona a coluna "IFE" (Índice de Força da Equipe): o nível ABSOLUTO
    estimado de cada seleção numa régua única — constante em todas as linhas
    da seleção, pois é um rating do time, não uma métrica do jogo.

    Motivação: o IDO é um resíduo vs expectativa, então NÃO compara seleções
    entre si (uma equipe fraca que surpreende pontua mais que uma forte que
    apenas confirma o favoritismo). O IFE recoloca a régua que o IDO descarta
    de propósito: as odds, que precificam todas as seleções na mesma escala
    global.

    IFE = rating de mercado + desempenho acima do mercado:

      1. Rating de mercado — mínimos quadrados sobre o sistema em que, para
         cada jogo, rating_sel − rating_adv ≈ xGD esperado pelo mercado (a
         mesma reta do IDO). Diferente da média simples de P(vitória), isso
         corrige o viés de calendário: quem caiu em grupo forte não é punido.
      2. Ajuste observado — média dos resíduos (xGD real − esperado) da
         seleção, encolhida por n/(n+4) para que 3-4 jogos de sorte/azar não
         movam demais o rating.

    Unidade: saldo de xG esperado por jogo contra um adversário médio da Copa.
    Propriedade útil: IFE(A) − IFE(B) ≈ xGD esperado de um hipotético A x B,
    mesmo que A e B nunca tenham se enfrentado.

    A coluna "IFE" gravada nos CSVs é a versão ESTÁTICA (todos os jogos). No
    dashboard o IFE é DINÂMICO: a régua (rating de mercado, parte 1) é sempre
    global — recalculá-la com um subconjunto estilhaçaria o grafo de
    confrontos —, mas o ajuste (parte 2) usa só os resíduos dos jogos
    selecionados. Com tudo selecionado, os dois batem. As colunas internas
    "_ife_mkt"/"_ife_res" alimentam essa versão dinâmica.

    Limitação conhecida: se o grafo de confrontos tiver "ilhas" (grupos ainda
    sem cruzamento no mata-mata), o nível relativo ENTRE ilhas fica impreciso
    — cada uma se ancora no próprio zero. É detectado e avisado no console e
    se resolve sozinho conforme as fases eliminatórias entram na base.

    `xgd_esp` e `resid` são Series alinhadas ao df (expectativa e resíduo por
    team-jogo); `ok` marca as linhas com xGD e odds válidos.
    """
    sub = df.loc[ok]
    teams = sorted(set(sub["selecao"]) | set(sub["adversario"]))
    if len(teams) < 3:
        return df
    ti = {t: i for i, t in enumerate(teams)}

    # Sistema sobredeterminado A·r = y: uma equação por team-jogo (cada jogo
    # entra 2x, uma por lado, o que simetriza o sistema) + uma linha soma(r)=0
    # que fixa a origem da escala no "adversário médio".
    n = len(sub)
    A = np.zeros((n + 1, len(teams)))
    A[np.arange(n), sub["selecao"].map(ti).to_numpy()] = 1.0
    A[np.arange(n), sub["adversario"].map(ti).to_numpy()] = -1.0
    A[n] = 1.0
    y = np.append(xgd_esp[ok].to_numpy(dtype=float), 0.0)
    mkt = pd.Series(np.linalg.lstsq(A, y, rcond=None)[0], index=teams)

    res_medio = resid[ok].groupby(sub["selecao"]).mean()
    n_jogos = sub.groupby("selecao")["event_id"].nunique()
    ajuste = (res_medio * n_jogos / (n_jogos + IFE_SHRINK)).reindex(teams).fillna(0.0)

    df["IFE"] = df["selecao"].map((mkt + ajuste).round(2))

    # Insumos do IFE DINÂMICO do dashboard: rating de mercado por seleção e
    # resíduo por team-jogo. São colunas internas — main() as extrai para o
    # payload e as remove antes de gravar os CSVs. Com elas o navegador
    # recompõe o IFE só com os jogos selecionados (mercado global + média dos
    # resíduos visíveis encolhida), sem resolver sistema nenhum no cliente.
    df["_ife_mkt"] = df["selecao"].map(mkt.round(4))
    df["_ife_res"] = resid.where(ok).round(4)

    print(f"  IFE: rating de mercado + desempenho observado "
          f"({n} team-jogos, {len(teams)} seleções)")
    _warn_isolated_groups(sub, teams)
    return df


def _warn_isolated_groups(sub, teams):
    """Avisa se o grafo de confrontos tem componentes isolados do principal —
    entre componentes diferentes a comparação de IFE é imprecisa."""
    viz = {t: set() for t in teams}
    for a, b in zip(sub["selecao"], sub["adversario"]):
        viz[a].add(b)
        viz[b].add(a)
    falta, comps = set(teams), []
    while falta:
        fila = [next(iter(falta))]
        comp = {fila[0]}
        while fila:
            for v in viz[fila.pop()]:
                if v not in comp:
                    comp.add(v)
                    fila.append(v)
        comps.append(comp)
        falta -= comp
    for comp in sorted(comps, key=len)[:-1]:      # todos menos o maior
        print("  [aviso] IFE: seleções ainda sem confronto (nem indireto) com "
              "o grupo principal — o nível delas vs as demais é impreciso: "
              + ", ".join(sorted(comp)))


def main():
    full_refresh = "--full" in sys.argv[1:] or "--force" in sys.argv[1:]

    season_id = resolve_season_id(UNIQUE_TOURNAMENT_ID, SEASON_YEAR)
    if not season_id:
        print(f"[erro] não achei a temporada {SEASON_YEAR} do torneio "
              f"{UNIQUE_TOURNAMENT_ID}.")
        sys.exit(1)
    print(f"== Copa {SEASON_YEAR} (torneio {UNIQUE_TOURNAMENT_ID}, "
          f"temporada {season_id}) ==")

    # Coleta incremental: carrega o que já temos e puxa só os jogos novos.
    if full_refresh:
        print("  (--full) ignorando cache: puxando TODOS os jogos.")
        existing_df, known_ids = None, set()
    else:
        existing_df, known_ids = load_existing(STATS_CSV)

    new_rows = collect_tournament(UNIQUE_TOURNAMENT_ID, season_id, known_ids)
    new_df = pd.DataFrame(new_rows) if new_rows else None

    # Junta linhas novas com as já existentes. Jogos re-puxados (ex.: antes sem
    # estatísticas) substituem a versão antiga para não duplicar.
    if new_df is not None and existing_df is not None:
        refreshed = set(new_df["event_id"])
        existing_df = existing_df[~existing_df["event_id"].isin(refreshed)]
        df = pd.concat([existing_df, new_df], ignore_index=True)
    elif new_df is not None:
        df = new_df
    else:
        df = existing_df

    if df is None or df.empty:
        print("\nNada coletado. Verifique conexão / fingerprint / IDs.")
        sys.exit(1)
    if new_df is None:
        print("  Nenhum jogo novo — reconstruindo as saídas com os dados em cache.")

    # IDO — índice de desempenho vs odds (derivado; usa xG + P(vitória) de TODOS os
    # jogos, por isso é calculado aqui, com o dataframe completo já montado).
    df = compute_performance_index(df)

    # Insumos do IFE dinâmico do dashboard (rating de mercado por seleção e
    # resíduo por linha). Saem do df aqui para NÃO vazarem para os CSVs.
    ife_mkt, ife_res = {}, None
    if "_ife_mkt" in df.columns:
        ife_mkt = {t: _json_num(v) for t, v in
                   df.groupby("selecao")["_ife_mkt"].first().items()}
        ife_res = df["_ife_res"]
        df = df.drop(columns=["_ife_mkt", "_ife_res"])

    # ordena colunas: identificação, o bloco do índice, depois as métricas da
    # API na ordem de STAT_LABELS. Estatísticas sem tradução (nome em inglês)
    # vão para o fim, nada some.
    id_cols = ["selecao", "adversario", "placar", "fase", "event_id"]
    index_cols = [c for c in INDEX_LABELS if c in df.columns]
    api_order = [lbl for lbl in dict.fromkeys(STAT_LABELS.values())
                 if lbl in df.columns and lbl not in index_cols]
    metric_order = index_cols + api_order
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
    df_out.to_csv(STATS_CSV, index=False, encoding="utf-8-sig")

    # ---- CSV resumo: agregado por seleção (subconjunto curado) ----
    # percentuais (rótulo com "(%)") e métricas do índice viram MÉDIA;
    # contagens viram SOMA.
    summary_cols = [c for c in SUMMARY_COLS if c in df.columns]
    mean_cols = {c for c in summary_cols if "(%)" in c or c in INDEX_LABELS}
    agg_map = {c: ("mean" if c in mean_cols else "sum") for c in summary_cols}
    agg = df.groupby("selecao")[summary_cols].agg(agg_map).round(2)

    # Consistência: nº de jogos e desvio-padrão do IDO por seleção. Desvio baixo
    # = a seleção rendeu de forma estável entre os jogos; alto = oscilou muito.
    # std de <2 jogos é indefinido -> 0.
    agg.insert(0, "Jogos", df.groupby("selecao")["event_id"].nunique())
    if "IDO" in agg.columns:
        desvio = df.groupby("selecao")["IDO"].std().round(1).fillna(0)
        agg.insert(agg.columns.get_loc("IDO") + 1, "IDO (desvio)", desvio)

    agg = agg.rename_axis(ID_LABELS["selecao"])
    agg.to_csv(RESUMO_CSV, encoding="utf-8-sig")

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
    for idx, r in df.iterrows():
        games.append({
            "selecao": r["selecao"],
            "adversario": r["adversario"],
            "placar": r["placar"],
            "fase": r["fase"],
            "event_id": int(r["event_id"]),
            # resíduo do jogo (real − esperado pelas odds) p/ o IFE dinâmico
            "ifeRes": _json_num(ife_res.loc[idx]) if ife_res is not None else None,
            "values": {m: _json_num(r[m]) for m in all_metrics},
        })
    phases = [p for p in PHASE_ORDER if p in set(df["fase"])]
    build_dashboard(games, groups, "dashboard.html",
                    phases=phases, descriptions=STAT_DESCRIPTIONS,
                    ife_mkt=ife_mkt, ife_shrink=IFE_SHRINK,
                    dims=DIMENSOES, dims_baseline=baseline_dimensoes(df),
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
