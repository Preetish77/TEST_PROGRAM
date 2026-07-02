import importlib
import io
from datetime import date, datetime

import streamlit as st

import analyzer
import ko_parser

importlib.reload(ko_parser)
importlib.reload(analyzer)

analyze_file = analyzer.analyze_file
filter_rows = analyzer.filter_rows
get_export_metadata = analyzer.get_export_metadata
read_csv_rows = analyzer.read_csv_rows

st.set_page_config(
    page_title="Campaign Export Analyzer",
    page_icon="📊",
    layout="wide",
)

st.title("Campaign Export Analyzer")
st.caption(
    "Step 1: Upload export and select **campaign** + **timestamp**. "
    "Step 2: Upload **KO Creative Details**. "
    "KO validation uses **delivered** rows only. "
    "EM01/03/05 = Initial SL · EM02/04/06 = Echo SL."
)

# --- Step 1: Export upload ---
uploaded = st.file_uploader(
    "Step 1 — Campaign export CSV",
    type=None,
    help="Comma-delimited export (with or without .csv extension)",
)

campaign_name = None
timestamp_from = None
timestamp_to = None

if uploaded:
    export_bytes = uploaded.getvalue()
    st.session_state["export_bytes"] = export_bytes
    st.session_state["export_name"] = uploaded.name

    fields, rows = read_csv_rows(io.BytesIO(export_bytes))
    meta = get_export_metadata(rows)
    st.session_state["export_meta"] = meta

    st.success(f"Export loaded: **{uploaded.name}** ({len(rows):,} rows)")

    st.subheader("Step 1 — Select campaign & timestamp")
    if meta["campaign_names"]:
        campaign_name = st.selectbox(
            "Campaign name",
            options=meta["campaign_names"],
            help="Only rows for this campaign will be analyzed",
        )
    else:
        st.error("No campaign_name values found in export.")
        campaign_name = st.text_input("Campaign name (manual)")

    c1, c2 = st.columns(2)
    default_min = (
        datetime.strptime(meta["timestamp_min"], "%Y-%m-%d").date()
        if meta.get("timestamp_min")
        else date.today()
    )
    default_max = (
        datetime.strptime(meta["timestamp_max"], "%Y-%m-%d").date()
        if meta.get("timestamp_max")
        else date.today()
    )
    with c1:
        timestamp_from = st.date_input("Timestamp from", value=default_min)
    with c2:
        timestamp_to = st.date_input("Timestamp to", value=default_max)

    preview = filter_rows(rows, campaign_name, timestamp_from, timestamp_to)
    delivered = sum(1 for r in preview if (r.get("status") or "").strip().lower() == "delivered")
    st.info(
        f"Preview: **{len(preview):,}** rows match filters · **{delivered:,}** delivered "
        f"(KO comparison uses delivered only)"
    )

# --- Step 2: KO upload (required) ---
st.subheader("Step 2 — KO document (required)")
ko_uploaded = st.file_uploader(
    "KO Creative Details (.csv or .xlsx)",
    type=None,
    help="JHM - Cancer - Internal ATE KO Document — Creative details sheet",
)

if st.button("Analyze & validate", type="primary", disabled=not uploaded):
    if not ko_uploaded:
        st.error("KO document is required. Upload the Creative Details file in Step 2.")
    elif not campaign_name:
        st.error("Select a campaign name in Step 1.")
    else:
        with st.spinner("Analyzing delivered rows and validating against KO…"):
            try:
                report = analyze_file(
                    io.BytesIO(st.session_state["export_bytes"]),
                    st.session_state.get("export_name", uploaded.name),
                    io.BytesIO(ko_uploaded.getvalue()),
                    ko_uploaded.name,
                    campaign_name=campaign_name,
                    timestamp_from=timestamp_from,
                    timestamp_to=timestamp_to,
                    require_ko=True,
                )
                st.session_state["report"] = report
            except Exception as exc:
                st.error(str(exc))

if "report" in st.session_state:
    d = st.session_state["report"]
    ex = d["extracts"]
    summ = d["export_summary"]
    validation = d["ko_validation"]

    st.divider()
    st.subheader("Filters applied")
    st.json(d["filters_applied"])

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Rows (filtered)", f"{d['row_count']:,}")
    m2.metric("Delivered", summ["row_counts"]["delivered_after_filter"])
    m3.metric("SL rows (delivered)", ex["export_sl_row_count"])
    m4.metric("KO matches", validation["match_count"])
    m5.metric("KO mismatches", validation["mismatch_count"])

    if validation["mismatch_count"] == 0 and validation["export_only_count"] == 0 and validation["ko_only_count"] == 0:
        st.success("All delivered SL and Keycode 4 values match the KO document.")
    else:
        st.warning(
            f"Mismatches: {validation['mismatch_count']} · "
            f"Export only: {validation['export_only_count']} · "
            f"KO only: {validation['ko_only_count']}"
        )

    st.subheader("KO validation (delivered rows only)")
    st.caption(
        "Strict comparison on **JN + Send + Keycode 4 + subject** (special characters must match exactly). "
        "**Special character mismatch** = same words but different dashes/hyphens (`‑`, `—`, `?`, etc.)."
    )
    all_results = (
        validation["matched"]
        + validation["mismatches"]
        + validation["export_only"]
        + validation["ko_only"]
    )
    if all_results:
        display_rows = [
            {
                "Status": r["status"],
                "JN": r["jn"],
                "Send": r["send"],
                "Keycode 4": r["keycode4"],
                "Export Subject": r["export_subject"],
                "KO Subject": r["ko_subject"],
            }
            for r in all_results
        ]
        st.dataframe(display_rows, use_container_width=True, hide_index=True)
    st.download_button(
        "Download validation report.csv",
        data=d["exports"]["validation_csv"],
        file_name="ko_validation_report.csv",
        mime="text/csv",
    )

    st.subheader("Keycode 4 vs c_creative_id (export check)")
    st.caption(
        "Keycode 4 = **stream** + **|** + **c_creative_id** (e.g. `stream1|breast`). "
        "This checks the creative part after `|` matches **c_creative_id** in the export."
    )
    kc = d.get("keycode4_validation", {})
    if kc:
        k1, k2, k3 = st.columns(3)
        k1.metric("Keycode 4 OK", kc["match_count"])
        k2.metric("Mismatches", kc["mismatch_count"])
        k3.metric("Incomplete rows", kc["incomplete_count"])
        if kc["mismatch_count"] == 0 and kc["incomplete_count"] == 0:
            st.success("All Keycode 4 values align with c_stream_id and c_creative_id.")
        elif kc["mismatch_count"] or kc["incomplete_count"]:
            st.warning("Some Keycode 4 / c_creative_id combinations need review.")
        if kc["rows"]:
            st.dataframe(
                [
                    {
                        "Stream": r["c_stream_id"],
                        "c_creative_id": r["c_creative_id"],
                        "Keycode 4": r["keycode4"],
                        "Creative part (after |)": r["keycode4_creative_part"],
                        "Creative match": r["creative_match"],
                        "Stream match": r["stream_match"],
                        "Status": r["status"],
                    }
                    for r in kc["rows"]
                ],
                use_container_width=True,
                hide_index=True,
            )
        st.download_button(
            "Download keycode4 validation.csv",
            data=d["exports"]["keycode4_validation_csv"],
            file_name="keycode4_creative_validation.csv",
            mime="text/csv",
        )

    st.subheader("Export SL rows (delivered)")
    st.caption("EM01 → Initial: SL · EM02 → Echo: SL · EM03 → Initial · EM04 → Echo …")
    st.dataframe(
        [
            {
                "JN": r["jn"],
                "Order": r["c_order_id"],
                "Send": r["send"],
                "Export SL": r["subject"],
                "c_creative_id": r["c_creative_id"],
                "Keycode 4": r["keycode4"],
                "Stream": r["c_stream_id"],
            }
            for r in ex["export_sl_rows"]
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Download KO-aligned export.csv",
        data=d["exports"]["ko_aligned_csv"],
        file_name="ko_aligned_export.csv",
        mime="text/csv",
    )

    st.subheader("Export summary")
    sc1, sc2 = st.columns(2)
    with sc1:
        st.markdown("**Consent categories** (delivered)")
        st.dataframe(summ["consent_categories"], use_container_width=True, hide_index=True)
        st.markdown("**Snippets used** (delivered)")
        st.dataframe(summ["snippets"], use_container_width=True, hide_index=True)
    with sc2:
        st.markdown("**EM → Initial / Echo** (delivered)")
        st.dataframe(summ["em_initial_echo"], use_container_width=True, hide_index=True)
        st.markdown("**Status breakdown** (filtered rows)")
        st.dataframe(summ["status_breakdown"], use_container_width=True, hide_index=True)

    with st.expander("Senders & integrations"):
        st.dataframe(summ["senders"], use_container_width=True, hide_index=True)
        st.dataframe(summ["integrations"], use_container_width=True, hide_index=True)

    st.caption(
        f"Timestamp range in filter: {summ['timestamp_range']['earliest']} → "
        f"{summ['timestamp_range']['latest']} · "
        f"Campaign IDs: {', '.join(summ['campaign_ids']) or 'n/a'}"
    )

st.divider()
st.caption("Files processed in memory only — not stored on the server.")
