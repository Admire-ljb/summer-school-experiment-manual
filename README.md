# Palm-sized UAV Experiment Manual

ReadTheDocs-style bilingual documentation generated from `D:/暑期学校/实验手册`.

- Organized by experiment number rather than by date.
- `zh/` contains the extracted Chinese source pages, including text, tables, links, commands, and figures.
- `en/` contains objective English experiment-document pages with language switches back to the Chinese source pages.
- `.github/workflows/pages.yml` deploys the static site with GitHub Pages Actions.

## Local preview

Open `index.html` in a browser, or serve this directory with any static file server.

## Regenerate

```bash
python tools/build_objective_docs.py
```
