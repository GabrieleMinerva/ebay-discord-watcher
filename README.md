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
