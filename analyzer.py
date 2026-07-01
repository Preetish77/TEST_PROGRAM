import csv
import io
import re
from collections import Counter
from datetime import datetime

from ko_parser import (
    build_keycode4,
    build_ko_aligned_csv,
    build_validation_csv,
    export_sl_display,
    normalize_sl,
    order_to_send,
    parse_ko_document,
    stream_id_to_keycode_stream,
    validate_export_against_ko,
)

JOB_NUMBER_FIELD = "c_job_number"
JN_PATTERN = re.compile(r"^\d{5}-\d{4}$")
NAMETOKEN_PATTERN = re.compile(r"\(\(\s*nametoken\s*\)\)", re.I)
SNIPPET_PATTERN = re.compile(r"snippet\s*\(\s*['\"]([^'\"]+)['\"]", re.I)
SNIPPET_MARKERS = ("{{ snippet", "{{snippet")
DELIVERED_STATUS = "delivered"


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


def extract_snippet_id(row):
    for field in ("subject", "message"):
        text = (row.get(field) or "").strip()
        match = SNIPPET_PATTERN.search(text)
        if match:
            return match.group(1)
    return None


def _parse_timestamp(value):
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00").split("+")[0])
    except ValueError:
        return None


def get_export_metadata(rows):
    campaigns = sorted({(r.get("campaign_name") or "").strip() for r in rows if (r.get("campaign_name") or "").strip()})
    timestamps = [_parse_timestamp(r.get("timestamp")) for r in rows if _parse_timestamp(r.get("timestamp"))]
    return {
        "campaign_names": campaigns,
        "timestamp_min": min(timestamps).date().isoformat() if timestamps else None,
        "timestamp_max": max(timestamps).date().isoformat() if timestamps else None,
    }


def filter_rows(rows, campaign_name=None, timestamp_from=None, timestamp_to=None):
    filtered = rows
    if campaign_name:
        filtered = [r for r in filtered if (r.get("campaign_name") or "").strip() == campaign_name.strip()]
    if timestamp_from or timestamp_to:
        start = datetime.combine(timestamp_from, datetime.min.time()) if timestamp_from else None
        end = datetime.combine(timestamp_to, datetime.max.time().replace(microsecond=0)) if timestamp_to else None
        kept = []
        for row in filtered:
            ts = _parse_timestamp(row.get("timestamp"))
            if ts is None:
                continue
            if start and ts < start:
                continue
            if end and ts > end:
                continue
            kept.append(row)
        filtered = kept
    return filtered


def build_export_summary(rows, campaign_name=None, timestamp_from=None, timestamp_to=None):
    """Summary of filtered export (all statuses + delivered subset)."""
    filtered = filter_rows(rows, campaign_name, timestamp_from, timestamp_to)
    delivered = [r for r in filtered if (r.get("status") or "").strip().lower() == DELIVERED_STATUS]

    consent = Counter((r.get("consent_category") or "").strip() or "(blank)" for r in delivered)
    snippets = Counter(extract_snippet_id(r) or "(none)" for r in delivered)
    senders = Counter((r.get("sender") or "").strip() or "(blank)" for r in delivered)
    integrations = Counter((r.get("integration_name") or "").strip() or "(blank)" for r in delivered)
    statuses = Counter((r.get("status") or "").strip() or "(blank)" for r in filtered)
    em_send = Counter()
    for r in delivered:
        order = (r.get("c_order_id") or "").strip()
        send = order_to_send(order)
        if order and send:
            em_send[f"{order} → {send}"] += 1

    campaign_ids = sorted({(r.get("campaign_id") or "").strip() for r in filtered if (r.get("campaign_id") or "").strip()})

    timestamps = [_parse_timestamp(r.get("timestamp")) for r in filtered if _parse_timestamp(r.get("timestamp"))]

    return {
        "filters": {
            "campaign_name": campaign_name or "(all)",
            "timestamp_from": str(timestamp_from) if timestamp_from else None,
            "timestamp_to": str(timestamp_to) if timestamp_to else None,
        },
        "row_counts": {
            "total_in_file": len(rows),
            "after_filter": len(filtered),
            "delivered_after_filter": len(delivered),
        },
        "campaign_ids": campaign_ids,
        "consent_categories": [{"name": k, "count": v} for k, v in consent.most_common()],
        "snippets": [{"snippet_id": k, "count": v} for k, v in snippets.most_common()],
        "senders": [{"sender": k, "count": v} for k, v in senders.most_common()],
        "integrations": [{"integration": k, "count": v} for k, v in integrations.most_common()],
        "status_breakdown": [{"status": k, "count": v} for k, v in statuses.most_common()],
        "em_initial_echo": [{"mapping": k, "delivered_events": v} for k, v in sorted(em_send.items())],
        "timestamp_range": {
            "earliest": min(timestamps).strftime("%Y-%m-%d %H:%M:%S") if timestamps else None,
            "latest": max(timestamps).strftime("%Y-%m-%d %H:%M:%S") if timestamps else None,
        },
    }


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


def split_keycode4(keycode4):
    text = (keycode4 or "").strip().lower()
    if "|" not in text:
        return None, None
    stream, creative = text.split("|", 1)
    return stream.strip(), creative.strip()


def validate_export_keycode4(rows, delivered_only=True):
    """
    Verify Keycode 4 in export aligns with c_stream_id and c_creative_id.
    Keycode 4 format: stream{N}|{c_creative_id} — creative part must match c_creative_id.
    """
    seen = {}
    incomplete = []

    for row in rows:
        if delivered_only and (row.get("status") or "").strip().lower() != DELIVERED_STATUS:
            continue

        stream_id = (row.get("c_stream_id") or "").strip()
        creative_id = (row.get("c_creative_id") or "").strip()
        jn = is_valid_jn(row.get(JOB_NUMBER_FIELD))
        order_id = (row.get("c_order_id") or "").strip()
        keycode4 = build_keycode4(stream_id, creative_id)

        if not stream_id or not creative_id or not keycode4:
            incomplete.append(
                {
                    "jn": jn or "",
                    "c_order_id": order_id,
                    "c_stream_id": stream_id,
                    "c_creative_id": creative_id,
                    "keycode4": keycode4 or "",
                    "status": "Incomplete (missing stream or creative)",
                }
            )
            continue

        k_stream, k_creative = split_keycode4(keycode4)
        expected_stream = stream_id_to_keycode_stream(stream_id)
        creative_id_lower = creative_id.lower()
        stream_ok = k_stream == expected_stream
        creative_ok = k_creative == creative_id_lower

        record = {
            "jn": jn or "",
            "c_order_id": order_id,
            "c_stream_id": stream_id,
            "c_creative_id": creative_id,
            "keycode4": keycode4.lower(),
            "keycode4_stream_part": k_stream,
            "keycode4_creative_part": k_creative,
            "expected_stream": expected_stream or "",
            "stream_match": "Yes" if stream_ok else "No",
            "creative_match": "Yes" if creative_ok else "No",
            "status": "OK" if stream_ok and creative_ok else "Mismatch",
        }
        dedupe_key = (stream_id, creative_id_lower, keycode4.lower())
        seen[dedupe_key] = record

    rows_out = sorted(
        seen.values(),
        key=lambda item: (item["c_stream_id"], item["c_creative_id"], item["keycode4"]),
    )
    matched = [r for r in rows_out if r["status"] == "OK"]
    mismatches = [r for r in rows_out if r["status"] == "Mismatch"]

    return {
        "rows": rows_out,
        "match_count": len(matched),
        "mismatch_count": len(mismatches),
        "incomplete_count": len(incomplete),
        "matched": matched,
        "mismatches": mismatches,
        "incomplete": incomplete,
    }


def build_keycode4_validation_csv(validation):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "c_stream_id",
            "c_creative_id",
            "keycode4",
            "keycode4_creative_part",
            "stream_match",
            "creative_match",
            "status",
            "jn",
            "c_order_id",
        ]
    )
    for row in validation["rows"] + validation["incomplete"]:
        writer.writerow(
            [
                row.get("c_stream_id", ""),
                row.get("c_creative_id", ""),
                row.get("keycode4", ""),
                row.get("keycode4_creative_part", ""),
                row.get("stream_match", ""),
                row.get("creative_match", ""),
                row.get("status", ""),
                row.get("jn", ""),
                row.get("c_order_id", ""),
            ]
        )
    return buf.getvalue()


def extract_export_sl_rows(rows, delivered_only=True):
    """Build unique SL rows from export. EM01/03/05=Initial, EM02/04/06=Echo. Delivered only by default."""
    seen = {}
    for row in rows:
        if delivered_only and (row.get("status") or "").strip().lower() != DELIVERED_STATUS:
            continue

        subject, has_nametoken = extract_subject_from_row(row)
        jn = is_valid_jn(row.get(JOB_NUMBER_FIELD))
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
            "subject_normalized": normalize_sl(subject),
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


def read_csv_rows(file_obj):
    text = file_obj.read()
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    rows = list(reader)
    return fields, rows


def analyze_file(
    file_obj,
    filename="upload",
    ko_file_obj=None,
    ko_filename=None,
    campaign_name=None,
    timestamp_from=None,
    timestamp_to=None,
    require_ko=True,
):
    """Analyze campaign export and validate against KO Creative Details (delivered rows only)."""
    if require_ko and ko_file_obj is None:
        raise ValueError("KO document is required. Upload the Creative Details file before validating.")

    fields, all_rows = read_csv_rows(file_obj)
    metadata = get_export_metadata(all_rows)
    filtered_rows = filter_rows(all_rows, campaign_name, timestamp_from, timestamp_to)

    if not filtered_rows:
        raise ValueError(
            "No rows match the selected campaign and timestamp range. "
            "Check campaign_name and dates."
        )

    export_summary = build_export_summary(all_rows, campaign_name, timestamp_from, timestamp_to)
    unique_subjects = extract_unique_subjects(
        [r for r in filtered_rows if (r.get("status") or "").strip().lower() == DELIVERED_STATUS]
    )
    unique_job_numbers = extract_unique_job_numbers(filtered_rows)
    export_sl_rows = extract_export_sl_rows(filtered_rows, delivered_only=True)
    keycode4_validation = validate_export_keycode4(filtered_rows, delivered_only=True)

    if not export_sl_rows:
        raise ValueError(
            "No delivered rows with valid JN, EM order, and subject line after filtering. "
            "KO comparison requires status=delivered."
        )

    status = Counter((r.get("status") or "").strip() or "(blank)" for r in filtered_rows)

    result = {
        "filename": filename,
        "row_count": len(filtered_rows),
        "row_count_total_file": len(all_rows),
        "column_count": len(fields),
        "metadata": metadata,
        "filters_applied": export_summary["filters"],
        "export_summary": export_summary,
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
            "keycode4_validation_csv": build_keycode4_validation_csv(keycode4_validation),
        },
        "keycode4_validation": keycode4_validation,
        "summary": {
            "delivered": status.get("delivered", 0),
            "enqueued": status.get("enqueued", 0),
            "opened": status.get("opened", 0),
            "clicked": status.get("clicked", 0),
        },
        "ko_validation": None,
    }

    ko_rows = parse_ko_document(ko_file_obj)
    validation = validate_export_against_ko(export_sl_rows, ko_rows)
    result["ko_validation"] = validation
    result["ko_filename"] = ko_filename or "KO document"
    result["exports"]["validation_csv"] = build_validation_csv(validation)
    result["ko_reference_count"] = len(ko_rows)

    return result
