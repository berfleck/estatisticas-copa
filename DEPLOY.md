# Deploy do dashboard na Railway

O servidor **não** roda o scraper. Você gera o `dashboard.html` na sua máquina,
commita e dá `git push`; a Railway detecta o push e faz redeploy sozinha,
servindo o arquivo estático. Público (sem senha).

```
Sua máquina                         GitHub            Railway
-----------                         ------            -------
python sofascore_stats.py  ──►  git push  ──►  redeploy automático ──►  URL pública
 (gera dashboard.html)                          (serve.py entrega o HTML)
```

## Arquivos do deploy

| Arquivo | Papel |
|---|---|
| `serve.py` | Servidor mínimo (stdlib) que entrega só o `dashboard.html` na `$PORT` |
| `Procfile` / `railway.json` | Dizem à Railway como iniciar (`python serve.py`) |
| `requirements.txt` | Vazio de propósito — o servidor não tem dependências |
| `requirements-local.txt` | Dependências do scraper (só na sua máquina) |
| `.gitignore` | Ignora `.venv/` e CSVs; mantém `dashboard.html` versionado |

## Setup (uma vez só)

1. **Inicializar o git e subir pro GitHub:**
   ```bash
   git init
   git add .
   git commit -m "dashboard Copa 2026 + deploy Railway"
   git branch -M main
   git remote add origin https://github.com/<voce>/<repo>.git
   git push -u origin main
   ```
2. **Na Railway:** New Project → *Deploy from GitHub repo* → selecione este repo.
3. A Railway builda com Nixpacks e roda `python serve.py`. Em *Settings → Networking*,
   clique **Generate Domain** para ter a URL pública.
4. Pronto — a URL mostra o dashboard.

## Atualizar os dados (sempre que quiser)

```bash
python sofascore_stats.py                 # regenera o dashboard.html
git add dashboard.html
git commit -m "atualiza estatisticas"
git push                                  # Railway redeploya sozinha (~1 min)
```

## Teste local do servidor (opcional)

```bash
python serve.py            # abre em http://localhost:8080
# ou defina a porta:  PORT=3000 python serve.py
```

## Notas

- **Sem risco de 403:** o servidor nunca fala com a Sofascore. Todo o scraping
  acontece na sua máquina (IP residencial), onde o `curl_cffi` funciona.
- **Build enxuto:** a Railway não instala `pandas`/`curl_cffi` (não estão no
  `requirements.txt`), então o deploy é rápido e leve.
