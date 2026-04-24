# eBay → Discord Watcher

Bot che traccia ricerche eBay e pubblica nuovi annunci su Discord.

## Setup locale

1. Installa Python 3.12+.
2. Installa dipendenze:
   ```bash
   pip install -r requirements.txt
   ```
3. Crea `.env` partendo da `.env.example` e valorizza almeno:
   - `EBAY_CLIENT_ID`
   - `EBAY_CLIENT_SECRET`
   - `DISCORD_WEBHOOK_URL`
4. Avvia:
   ```bash
   python -m app.main
   ```

## Configurazione

- Di default il bot legge `config.yaml`.
- Puoi cambiare file con `CONFIG_PATH`.
- In `config.render.yaml` puoi usare placeholder `${VAR}` che vengono risolti da variabili ambiente (utile per segreti).

## Deploy su Render (Docker + Worker)

Il repository include già i file necessari:

- `Dockerfile`
- `.dockerignore`
- `render.yaml`
- `config.render.yaml`

### Procedura consigliata

1. Push del repository su GitHub.
2. In Render: **New +** → **Blueprint**.
3. Seleziona repo, Render leggerà `render.yaml` e creerà un servizio `worker`.
4. Imposta i secret environment variables in Render (non nel repo):
   - `EBAY_CLIENT_ID`
   - `EBAY_CLIENT_SECRET`
   - `DISCORD_WEBHOOK_URL`
   - `DISCORD_WEBHOOK_URL_DEALS` (se usi route dedicate)
   - `GOOGLE_API_KEY` (opzionale per integrazioni future)
5. Aggiungi un **Persistent Disk** montato su `/var/data` (consigliato) per mantenere `posted_items.sqlite` tra i redeploy.

### Sicurezza API key

- Le chiavi **non** devono stare in `config.render.yaml`, `.env.example` o codice.
- Vanno inserite solo come secret in Render dashboard.
- Il file `render.yaml` usa `sync: false` per i secret: viene definita la variabile ma non il valore.

## Avvio container

Il container esegue automaticamente:

```bash
python -m app.main
```


## Protezione da rate-limit Discord

Per evitare `429 You are being rate limited`, puoi regolare queste variabili ambiente:

- `DISCORD_POST_DELAY_SECONDS` (default `0.4`): pausa tra un post e il successivo.
- `DISCORD_MAX_POSTS_PER_RUN` (default `8`): massimo annunci inviati per ogni ciclo scheduler.
- `DISCORD_MAX_RETRIES` (default `3`): retry automatici su risposta `429` rispettando `retry_after`.


## Multi-canale Discord (più hook, più filtri)

Ora una query può pubblicare su **più canali** con route dedicate (`queries[].routes`).
Ogni route può avere:

- `webhook_url` diverso
- `title_must_contain_any` / `title_must_not_contain_any`
- `price_min` / `price_max`

Esempio rapido:

```yaml
queries:
  - name: "game boy"
    keywords: "game boy"
    interval_seconds: 30
    routes:
      - name: "generale"
        webhook_url: "${DISCORD_WEBHOOK_URL}"
      - name: "occasioni"
        webhook_url: "${DISCORD_WEBHOOK_URL_DEALS}"
        price_max: 80
        title_must_not_contain_any: ["difetti", "non funzionante"]
```

> Se `routes` non è definito, resta valido il comportamento storico con `queries[].discord.webhook_url`.


## Nota su timeout deploy Render

Se per errore deployi come **Web Service** invece di **Worker**, Render aspetta una porta aperta e può andare in timeout.
L'app ora apre un endpoint health minimale (`/`) quando la env `PORT` è presente, così il deploy non fallisce anche in modalità web.
Resta comunque consigliato usare **Background Worker**.


Puoi anche ridurre il carico e il rischio 429 con `EBAY_SEARCH_LIMIT` (default `30`).
