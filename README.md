# Campaign Export Analyzer

Upload campaign export files and view delivery, engagement, and status reports in your browser.

**Live app:** Deploy on [Streamlit Cloud](https://share.streamlit.io) using `streamlit_app.py`.

## Files for deployment

- `streamlit_app.py` — web UI
- `analyzer.py` — analysis logic
- `requirements.txt` — dependencies
- `.streamlit/config.toml` — app settings

## Run locally

```bash
py -3 -m pip install -r requirements.txt
py -3 -m streamlit run streamlit_app.py
```
