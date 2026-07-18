# Palm-sized UAV Autonomous Systems Laboratory Manual

Bilingual experiment manual for palm-sized UAV summer school labs.

- The GitHub Pages root entry opens the English documentation by default.
- `zh/` contains Chinese experiment pages, including text, tables, links, commands, and figures.
- `en/` contains English experiment pages with language switches back to the Chinese pages.
- `.github/workflows/pages.yml` deploys the static site with GitHub Pages Actions.

## Course Materials

Download the `course-materials` folder from the [BUAA cloud link](https://bhpan.buaa.edu.cn/link/AA5DF49653676B4EDFBAB8B2A09B0FBEE9). The link is valid until 2028-11-11 10:31.

## Local preview

Open `index.html` in a browser, or serve this directory with any static file server.

## Maintenance

```bash
python tools/build_objective_docs.py
```
