# Handoff — Redesign do dashboard + dimensões compostas

Dois entregáveis:

1. **`dashboard-redesign.html`** — o novo dashboard completo (Painel, Comparar,
   Perfil), **vanilla JS, arquivo único, offline**. Substitui o `_TEMPLATE` do
   `dashboard.py`. Já traz o cálculo das 5 dimensões compostas rodando no cliente.
2. **Este documento** — como plugar no pipeline e (opcional) canonizar as dimensões
   no Python.

> Importante: `dashboard-redesign.html` é **autossuficiente**. As dimensões
> (Ataque, Finalização, Construção, Pressão, Defesa) são z-scores calculados no
> navegador a partir de uma régua global montada dos próprios `games` — inclusive
> o xG/grandes chances **concedidos**, obtidos da linha do adversário no mesmo
> jogo. Ou seja: para publicar o visual novo **não é preciso mudar a matemática do
> pipeline**. A parte Python (seções 3–6) é opcional, para deixar as dimensões
> canônicas nos CSVs.

---

## Prompt para colar no Claude Code

> No repositório `estatisticas-copa`, publique o novo dashboard: substitua o
> `_TEMPLATE` de `dashboard.py` pelo conteúdo de `dashboard-redesign.html`
> (mantendo o placeholder `__DATA__` no `<script id="viz-data">`). Garanta que o
> payload embutido inclua a chave `flags` (dict de bandeiras) DENTRO do DATA, e
> remova o antigo `const FLAGS = __FLAGS__;` — o redesign lê `DATA.flags`. Não
> altere o cálculo de IDO/IFE. Depois (opcional), canonize as dimensões seguindo
> as seções 3–6.

---

## 1. Publicar o visual novo (mínimo necessário)

Em `dashboard.py`:

1. Troque o conteúdo de `_TEMPLATE` pelo HTML de `dashboard-redesign.html`.
   Mantenha o placeholder no corpo: `<script id="viz-data" type="application/json">__DATA__</script>`.
2. O redesign lê **`DATA.flags`** (não usa mais `__FLAGS__`). No `build_dashboard`,
   inclua as bandeiras dentro do payload e pare de injetar `__FLAGS__`:

```python
payload = {
    "games": games, "groups": groups, "phases": phases or [],
    "descriptions": descriptions or {},
    "ifeMkt": ife_mkt or {}, "ifeShrink": ife_shrink,
    "flags": TEAM_FLAGS,          # <-- bandeiras vão DENTRO do DATA
    "generatedAt": generated_at,
}
html = _TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
```

Pronto — o dashboard novo já funciona, com as 5 dimensões calculadas no cliente.

**Contrato de dados que o redesign espera em `DATA`:** `games[]` (cada um com
`selecao, adversario, placar, fase, event_id, ifeRes, values{…}`), `groups[]`,
`phases[]`, `descriptions{}`, `ifeMkt{}`, `ifeShrink`, `flags{}`, `generatedAt`.
Tudo isso o `main()` atual já produz (só faltava `flags` dentro do payload).

---

## 2. As 5 dimensões (referência da fórmula)

Já implementadas em `dashboard-redesign.html` (constante `DIMS` + funções
`compVal`, `dimZ`, `dimScore`). Formato `[métrica, peso, inverter?]`:

- **Ataque** = xG(.40) · Grandes Chances(.25) · Chutes no Alvo(.20) · Finalizações(.15)
- **Finalização** = xG/finalização(.50) · %no alvo(.25) · Gr. Chances Convertidas(.25)
- **Construção** = Passes Certos(.45) · Posse %(.35) · Passes(.20)
- **Pressão** = Toques na Área(.30) · Chutes na Área(.20) · Entradas Últ. Terço(.20) · Ações Últ. Terço(.15) · Faltas Sofridas Últ. Terço(.15)
- **Defesa** = xG Concedido(.30, inv) · Gr. Chances Concedidas(.20, inv) · Gols Evitados(.12) · Defesas Difíceis(.08) · Desarmes(.10) · Interceptações(.10) · Recuperações(.06) · Duelos Ganhos %(.04)

Escore = média ponderada dos **z-scores** dos componentes (régua global fixa),
mapeada por `50 + 15·z` → 0–100 (50 = média da Copa). Raio do radar =
`clamp((z+2.5)/5, .03, 1)`.

---

## 3–6. (OPCIONAL) Canonizar as dimensões no pipeline Python

Faça isto só se quiser as dimensões gravadas nos CSVs / disponíveis fora do
dashboard. O visual **não depende disso**.

### 3. Colunas "sofridas" (linha do adversário)

Em `sofascore_stats.py`, após o cálculo do `xGD` (mesmo padrão de groupby):

```python
grp = df.groupby("event_id")
tot_xg = grp["xG (Gols Esperados)"].transform("sum")
df["xG Concedido"] = (tot_xg - df["xG (Gols Esperados)"]).round(2)
df.loc[grp["xG (Gols Esperados)"].transform("count") < 2, "xG Concedido"] = np.nan
tot_bc = grp["Grandes Chances"].transform("sum")
df["Grandes Chances Concedidas"] = (tot_bc - df["Grandes Chances"])
```

Adicione as duas a `STAT_GROUPS["Defesa"]` para não caírem em "Outras".

### 4. Spec + derivadas

```python
DIMENSOES = {
  "Ataque":      [("xG (Gols Esperados)",.40),("Grandes Chances",.25),("Chutes no Alvo",.20),("Finalizações",.15)],
  "Finalização": [("@xg_por_fin",.50),("@sot_pct",.25),("Grandes Chances Convertidas",.25)],
  "Construção":  [("Passes Certos",.45),("Posse de Bola (%)",.35),("Passes",.20)],
  "Pressão":     [("Toques na Área",.30),("Chutes Dentro da Área",.20),("Entradas no Último Terço",.20),("Ações no Último Terço",.15),("Faltas Sofridas no Último Terço",.15)],
  "Defesa":      [("xG Concedido",.30,True),("Grandes Chances Concedidas",.20,True),("Gols Evitados",.12),("Defesas Difíceis",.08),("Desarmes",.10),("Interceptações",.10),("Recuperações de Bola",.06),("Duelos Ganhos (%)",.04)],
}
_DERIVADAS = {
  "@xg_por_fin": lambda d: d["xG (Gols Esperados)"] / d["Finalizações"].where(d["Finalizações"]>0),
  "@sot_pct":    lambda d: d["Chutes no Alvo"]      / d["Finalizações"].where(d["Finalizações"]>0),
}
def _valor_componente(df, key):
    return _DERIVADAS[key](df) if key in _DERIVADAS else pd.to_numeric(df[key], errors="coerce")
```

### 5. Régua global (baseline)

```python
def baseline_dimensoes(df):
    comps = {c for comps in DIMENSOES.values() for (c, *_) in comps}
    return {c: {"mean": round(float(s.mean()),4), "sd": round(float(s.std() or 1),4)}
            for c in comps for s in [ _valor_componente(df, c).dropna() ]}
```

Passe `dims=DIMENSOES, dims_baseline=baseline_dimensoes(df)` para `build_dashboard`
e inclua `"dims"` / `"dimsBaseline"` no payload (camelCase: `dims`, `dimsBaseline`).

### 6. Fazer o front-end usar a régua do Python (em vez de calcular)

Em `dashboard-redesign.html`, no `boot()`, se `data.dimsBaseline` existir, use-o em
vez de `buildIndex()`; e ajuste `DIMS`/`compVal` para as chaves do Python
(`@xg_por_fin`, `@sot_pct`, e `xG Concedido`/`Grandes Chances Concedidas` como
métricas normais já presentes em `values`). O resto de `dimZ`/`dimScore` é igual.

---

## Checklist

- [ ] Dashboard novo abre e navega (Painel/Comparar/Perfil).
- [ ] `flags` está dentro do `DATA`; bandeiras aparecem.
- [ ] Excluir/incluir jogos recalcula IFE, IDO e dimensões.
- [ ] IDO/IFE inalterados vs. versão atual.
- [ ] (Opcional) `xG Concedido`/`Grandes Chances Concedidas` no CSV; `dimsBaseline` no payload.

## Calibração

Único ponto de sintonia: os **pesos** em `DIMS`/`DIMENSOES` e o fator `15` em
`50 + 15·z` (maior = escores mais espalhados). O resto é automático.
