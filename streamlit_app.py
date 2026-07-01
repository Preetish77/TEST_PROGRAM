import io
import json

import streamlit as st

from analyzer import analyze_file

st.set_page_config(
    page_title="Campaign Export Analyzer",
    page_icon="📊",
    layout="wide",
)

st.title("Campaign Export Analyzer")
st.caption("Upload a comma-delimited campaign export file. Works in any browser — no install needed.")

uploaded = st.file_uploader(
    "Choose your export file",
    type=["csv", "txt"],
    help="CSV or comma-delimited export (max 50 MB)",
)

if uploaded:
    st.success(f"Selected: **{uploaded.name}** ({uploaded.size:,} bytes)")

    if st.button("Analyze file", type="primary", use_container_width=False):
        with st.spinner("Analyzing…"):
            try:
                report = analyze_file(io.BytesIO(uploaded.getvalue()), uploaded.name)
                st.session_state["report"] = report
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")

if "report" in st.session_state:
    d = st.session_state["report"]
    eng = d["engagement"]

    st.divider()
    st.subheader("Summary")

    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("Rows", f"{d['row_count']:,}")
    c2.metric("Columns", d["column_count"])
    c3.metric("Recipients", f"{d['recipients']['unique_count']:,}")
    c4.metric("Templates", d["templates"]["unique_count"])
    c5.metric("Open rate", f"{eng['open_rate']}%" if eng["open_rate"] is not None else "—")
    c6.metric("Click rate", f"{eng['click_rate']}%" if eng["click_rate"] is not None else "—")
    c7.metric("Errors", d["errors_count"])

    st.subheader("Campaign")
    if d["campaign"]:
        st.json(d["campaign"])
    else:
        st.info("No campaign metadata found in the file.")

    if d["date_range"]["earliest"]:
        st.write(
            f"**Date range:** {d['date_range']['earliest']} → {d['date_range']['latest']}"
        )

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Status breakdown")
        st.dataframe(
            [{"Status": s["name"], "Count": s["count"]} for s in d["status"]],
            use_container_width=True,
            hide_index=True,
        )

    with col_b:
        st.subheader("Engagement")
        st.dataframe(
            [
                {"Metric": "Delivered (unique)", "Value": eng["delivered_pairs"]},
                {"Metric": "Opened (unique)", "Value": eng["opened_pairs"]},
                {"Metric": "Clicked (unique)", "Value": eng["clicked_pairs"]},
                {"Metric": "Open events (total)", "Value": eng["opened_events"]},
                {"Metric": "Click events (total)", "Value": eng["clicked_events"]},
            ],
            use_container_width=True,
            hide_index=True,
        )

    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Streams")
        st.dataframe(
            [{"Stream": s["name"], "Events": s["count"]} for s in d["streams"]],
            use_container_width=True,
            hide_index=True,
        )

    with col_d:
        st.subheader("Top recipients")
        st.dataframe(
            [{"Email": r["email"], "Events": r["count"]} for r in d["recipients"]["top"]],
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Email templates", expanded=False):
        st.dataframe(
            [{"Template": t["name"], "Events": t["count"]} for t in d["templates"]["items"]],
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Status by stream", expanded=False):
        for block in d["status_by_stream"]:
            parts = ", ".join(f"{b['status']}: {b['count']:,}" for b in block["breakdown"])
            st.markdown(f"**{block['stream']}** — {parts}")

    st.download_button(
        "Download report (JSON)",
        data=json.dumps(d, indent=2),
        file_name=f"report_{d['filename']}.json",
        mime="application/json",
    )

st.divider()
st.caption("Files are analyzed in memory and are not stored on the server.")
