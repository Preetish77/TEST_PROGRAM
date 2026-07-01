import csv
import io
import re
from collections import Counter

from ko_parser import (
    build_keycode4,
    build_ko_aligned_csv,
    build_validation_csv,
    export_sl_display,
    normalize_sl,
    order_to_send,
    parse_ko_document,
    validate_export_against_ko,
)

JOB_NUMBER_FIELD = "c_job_number"
JN_PATTERN = re.compile(r"^\d{5}-\d{4}$")
NAMETOKEN_PATTERN = re.compile(r"\(\(\s*nametoken\s*\)\)", re.I)
SNIPPET_MARKERS = ("{{ snippet", "{{snippet")


def _is_snippet(value):
    text = (value or "").strip()
    if not text:
        return True
    if any(text.lower().startswith(m) for m in SNIPPET_MARKERS):
        return True
    if text.startswith("{{") and text.endswith("}}"):
        return True
    return False


def _has_nametoken(value):
    return bool(NAMETOKEN_PATTERN.search(value or ""))


def _normalize_nametoken(value):
    text = (value or "").strip()
    if not text:
        return text
    if _has_nametoken(text):
        rest = NAMETOKEN_PATTERN.sub("", text, count=1).strip()
        return f"((NAMETOKEN)) {rest}".strip() if rest else "((NAMETOKEN))"
    return text


def extract_subject_from_row(row):
    c_subject = (row.get("c_subject") or "").strip()
    subject = (row.get("subject") or "").strip()

    if c_subject and _has_nametoken(c_subject):
        return _normalize_nametoken(c_subject), True

    if c_subject and not _is_snippet(c_subject):
        return c_subject, False

    if subject and not _is_snippet(subject):
        return subject, False

    return None, False


def extract_unique_subjects(rows):
    subjects = {}
    for row in rows:
        text, has_token = extract_subject_from_row(row)
        if text:
            subjects[text] = subjects.get(text, False) or has_token
    return [{"subject": s, "has_nametoken": subjects[s]} for s in sorted(subjects)]


def is_valid_jn(value):
    text = (value or "").strip()
    if JN_PATTERN.fullmatch(text):
        return text
    return None


def extract_unique_job_numbers(rows):
    job_numbers = set()
    for row in rows:
        jn = is_valid_jn(row.get(JOB_NUMBER_FIELD))
        if jn:
            job_numbers.add(jn)
    return sorted(job_numbers)


def extract_export_sl_rows(rows):
    """Build unique SL rows from campaign export CSV."""
    seen = {}
    for row in rows:
        subject, has_nametoken = extract_subject_from_row(row)
        jn = is_valid_jn(row.get("c_job_number"))
        stream_id = (row.get("c_stream_id") or "").strip()
        order_id = (row.get("c_order_id") or "").strip()
        creative_id = (row.get("c_creative_id") or "").strip()
        action_name = (row.get("action_name") or "").strip()
        send = order_to_send(order_id)

        if not subject or not jn or not send:
            continue

        keycode4 = build_keycode4(stream_id, creative_id)
        ko_subject = export_sl_display(subject, has_nametoken)
        record = {
            "action_name": action_name,
            "jn": jn,
            "c_stream_id": stream_id,
            "c_order_id": order_id,
            "send": send,
            "subject": subject,
            "subject_ko_format": ko_subject,
            "subject_normalized": normalize_sl(ko_subject),
            "keycode4": (keycode4 or "").lower(),
            "c_creative_id": creative_id,
            "has_nametoken": has_nametoken,
            "personalization": "Yes" if has_nametoken else "No",
        }
        dedupe_key = (jn, send, keycode4 or "", record["subject_normalized"])
        seen[dedupe_key] = record

    return sorted(
        seen.values(),
        key=lambda item: (item["jn"], item["send"], item["keycode4"], item["subject_normalized"]),
    )


def build_subjects_csv(subjects):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["subject", "has_nametoken"])
    for item in subjects:
        writer.writerow([item["subject"], "Yes" if item["has_nametoken"] else "No"])
    return buf.getvalue()


def build_job_numbers_csv(job_numbers):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["JN"])
    for job in job_numbers:
        writer.writerow([job])
    return buf.getvalue()


def _read_csv_rows(file_obj):
    text = file_obj.read()
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    rows = list(reader)
    return fields, rows


def analyze_file(file_obj, filename="upload", ko_file_obj=None, ko_filename=None):
    """Analyze campaign export CSV and optionally validate against KO Creative Details."""
    fields, rows = _read_csv_rows(file_obj)

    unique_subjects = extract_unique_subjects(rows)
    unique_job_numbers = extract_unique_job_numbers(rows)
    export_sl_rows = extract_export_sl_rows(rows)

    status = Counter((r.get("status") or "").strip() or "(blank)" for r in rows)
    timestamps = [(r.get("timestamp") or "").strip() for r in rows if (r.get("timestamp") or "").strip()]

    errors = [
        r
        for r in rows
        if (r.get("error") or "").strip()
        or (r.get("status") or "").strip().lower() in ("failed", "bounced", "rejected", "hard_bounce")
    ]

    result = {
        "filename": filename,
        "row_count": len(rows),
        "column_count": len(fields),
        "date_range": {
            "earliest": min(timestamps) if timestamps else None,
            "latest": max(timestamps) if timestamps else None,
        },
        "extracts": {
            "unique_subjects": unique_subjects,
            "unique_subject_count": len(unique_subjects),
            "unique_job_numbers": unique_job_numbers,
            "unique_job_number_count": len(unique_job_numbers),
            "export_sl_rows": export_sl_rows,
            "export_sl_row_count": len(export_sl_rows),
        },
        "exports": {
            "subjects_csv": build_subjects_csv(unique_subjects),
            "job_numbers_csv": build_job_numbers_csv(unique_job_numbers),
            "ko_aligned_csv": build_ko_aligned_csv(export_sl_rows),
        },
        "summary": {
            "delivered": status.get("delivered", 0),
            "enqueued": status.get("enqueued", 0),
            "opened": status.get("opened", 0),
            "clicked": status.get("clicked", 0),
            "errors_count": len(errors),
        },
        "ko_validation": None,
    }

    if ko_file_obj is not None:
        ko_rows = parse_ko_document(ko_file_obj)
        validation = validate_export_against_ko(export_sl_rows, ko_rows)
        result["ko_validation"] = validation
        result["ko_filename"] = ko_filename or "KO document"
        result["exports"]["validation_csv"] = build_validation_csv(validation)
        result["ko_reference_count"] = len(ko_rows)

    return result
