# eBay → Discord Watcher

Bot Python che monitora ricerche eBay e pubblica nuovi annunci su Discord.

## Setup

1) Installa dipendenze  
pip install -r requirements.txt

2) Crea file .env con:
EBAY_CLIENT_ID
EBAY_CLIENT_SECRET

3) Configura config.yaml:
- keywords ricerca
- webhook Discord

4) Avvia:
python -m app.main
