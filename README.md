# Campaign Export Analyzer

Upload campaign export files and view delivery, engagement, and status reports in your browser.

**Live app:** Deploy on [Streamlit Cloud](https://share.streamlit.io) using `streamlit_app.py`.

## Files for deployment

- `streamlit_app.py` — web UI
- `analyzer.py` — analysis logic
- `requirements.txt` — dependencies
- `.streamlit/config.toml` — app settings

## Run locally (no Streamlit)

Double-click **`START_APP.bat`** in the project folder, or run:

```bash
py -3 -m pip install -r requirements.txt
py -3 app.py
```

Your browser opens at **http://localhost:5000** — runs only on your computer.

Optional: `py -3 app.py --share` lets others on your Wi‑Fi use `http://YOUR-IP:5000`.

## Streamlit version (optional)

```bash
py -3 -m streamlit run streamlit_app.py
```
