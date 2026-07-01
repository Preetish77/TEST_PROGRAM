import io

import streamlit as st

from analyzer import analyze_file

st.set_page_config(
    page_title="Campaign Export Analyzer",
    page_icon="📊",
    layout="wide",
)

st.title("Campaign Export Analyzer")
st.caption(
    "Upload your campaign export CSV and optional KO document. "
    "Validates subject lines (SL) and Keycode 4 against the KO doc."
)

col1, col2 = st.columns(2)

with col1:
    uploaded = st.file_uploader(
        "Campaign export CSV",
        type=None,
        help="Comma-delimited export (.csv, .txt, or no extension — e.g. P_JHM_Cancer_ATE_260625)",
    )

with col2:
    ko_uploaded = st.file_uploader(
        "KO document (Creative details)",
        type=None,
        help="KO Creative details sheet as .csv or .xlsx",
    )

if uploaded:
    st.info(f"Export: **{uploaded.name}** ({uploaded.size:,} bytes)")
if ko_uploaded:
    st.info(f"KO doc: **{ko_uploaded.name}**")

if uploaded and st.button("Analyze & validate", type="primary"):
    with st.spinner("Analyzing export and validating against KO…"):
        try:
            export_bytes = uploaded.getvalue()
            ko_bytes = ko_uploaded.getvalue() if ko_uploaded else None

            report = analyze_file(
                io.BytesIO(export_bytes),
                uploaded.name,
                io.BytesIO(ko_bytes) if ko_bytes else None,
                ko_uploaded.name if ko_uploaded else None,
            )
            st.session_state["report"] = report
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")

if "report" in st.session_state:
    d = st.session_state["report"]
    ex = d["extracts"]
    summ = d["summary"]
    validation = d.get("ko_validation")

    st.divider()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("CSV rows", f"{d['row_count']:,}")
    m2.metric("Unique subjects", ex["unique_subject_count"])
    m3.metric("Unique JN", ex["unique_job_number_count"])
    m4.metric("SL rows (export)", len(ex["export_sl_rows"]))
    if validation:
        m5.metric("KO matches", validation["match_count"])
    else:
        m5.metric("Delivered", summ["delivered"])

    if validation:
        st.subheader("KO validation — SL & Keycode 4")
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("Matched", validation["match_count"])
        v2.metric("Subject mismatches", validation["mismatch_count"])
        v3.metric("Not in KO", validation["export_only_count"])
        v4.metric("Missing from export", validation["ko_only_count"])

        all_results = (
            validation["matched"]
            + validation["mismatches"]
            + validation["export_only"]
            + validation["ko_only"]
        )
        if all_results:
            st.dataframe(all_results, use_container_width=True, hide_index=True)

        if validation["mismatch_count"] == 0 and validation["export_only_count"] == 0 and validation["ko_only_count"] == 0:
            st.success("All SL and Keycode 4 values match the KO document.")
        elif validation["mismatch_count"] or validation["export_only_count"] or validation["ko_only_count"]:
            st.warning("Some rows do not match the KO document. Review the table above.")

        st.download_button(
            "Download validation report.csv",
            data=d["exports"]["validation_csv"],
            file_name="ko_validation_report.csv",
            mime="text/csv",
        )
    elif not ko_uploaded:
        st.info(
            "Upload the KO **Creative details** CSV to validate SL and Keycode 4. "
            "In Excel: open the KO workbook → Creative details sheet → Save As CSV."
        )

    st.subheader("KO-aligned export (SL rows)")
    st.caption(
        "Columns match the KO document: JN, Send, Subject Lines, Personalization, Keycode 4. "
        "Personalized subjects use **[INS1]** as in the KO doc."
    )
    if ex["export_sl_rows"]:
        st.dataframe(
            [
                {
                    "JN": r["jn"],
                    "Send": r["send"],
                    "Subject (KO format)": r["subject_ko_format"],
                    "Personalization": r["personalization"],
                    "Keycode 4": r["keycode4"],
                    "Stream": r["c_stream_id"],
                    "Creative code": r["c_creative_id"],
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

    with st.expander("Unique subject lines (export format)"):
        if ex["unique_subjects"]:
            st.dataframe(
                [
                    {
                        "#": i + 1,
                        "subject": item["subject"],
                        "has_nametoken": "Yes" if item["has_nametoken"] else "No",
                    }
                    for i, item in enumerate(ex["unique_subjects"])
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "Download subjects.csv",
                data=d["exports"]["subjects_csv"],
                file_name="unique_subjects.csv",
                mime="text/csv",
            )

    with st.expander("Unique job numbers (JN)"):
        if ex["unique_job_numbers"]:
            st.dataframe(
                [{"#": i + 1, "JN": j} for i, j in enumerate(ex["unique_job_numbers"])],
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "Download JN.csv",
                data=d["exports"]["job_numbers_csv"],
                file_name="unique_JN.csv",
                mime="text/csv",
            )

st.divider()
st.caption("Files are processed in memory only and are not stored on the server.")
