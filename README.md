# rankandrent-sites

Mirror pubblico dei siti lead-gen del progetto Rank&Rent (build + deploy GitHub Pages).

- Sorgente strategico (dati, docs, tracker): repo privato `FrancescoWM/rankandrent`
- Ogni sito vive in `sites/<site-id>/` — pagine sorgente in `src/pages/`, config in `site.json`
- Build: `python3 tools/build.py sites/<site-id> --url <origin> --base /<site-id>`
- Deploy: GitHub Action su push di `sites/**` o `tools/**` -> GitHub Pages
- Gli URL `*.github.io/rankandrent-sites/<site-id>/` sono ANTEPRIME (meta noindex):
  l'indicizzazione si attiva al bind del dominio finale.

## Anteprime live

- fabbro-padova: https://francescowm.github.io/rankandrent-sites/fabbro-padova/
- idraulico-firenze: https://francescowm.github.io/rankandrent-sites/idraulico-firenze/
- traslochi-firenze: https://francescowm.github.io/rankandrent-sites/traslochi-firenze/
