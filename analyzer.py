import csv
import io
from collections import Counter, defaultdict


def analyze_file(file_obj, filename="upload"):
    """Analyze a campaign export CSV and return a JSON-serializable report."""
    text = file_obj.read()
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    rows = list(reader)

    status = Counter((r.get("status") or "").strip() or "(blank)" for r in rows)
    recipients = Counter(
        (r.get("recipient") or "").strip() for r in rows if (r.get("recipient") or "").strip()
    )
    actions = Counter(
        (r.get("action_name") or "").strip() for r in rows if (r.get("action_name") or "").strip()
    )
    streams = Counter(
        (r.get("c_stream_id") or "").strip() for r in rows if (r.get("c_stream_id") or "").strip()
    )
    types = Counter((r.get("type") or "").strip() or "(blank)" for r in rows)

    timestamps = [(r.get("timestamp") or "").strip() for r in rows if (r.get("timestamp") or "").strip()]

    campaign_fields = [
        "campaign_id",
        "campaign_name",
        "campaign_policy",
        "campaign_trigger",
        "consent_category",
        "c_audience_id",
        "c_job_number",
    ]
    campaign = {}
    if rows:
        for key in campaign_fields:
            val = (rows[0].get(key) or "").strip()
            if val:
                campaign[key] = val

    errors = [
        r
        for r in rows
        if (r.get("error") or "").strip()
        or (r.get("status") or "").strip().lower() in ("failed", "bounced", "rejected", "hard_bounce")
    ]

    delivered_pairs = set()
    opened_pairs = set()
    clicked_pairs = set()
    for r in rows:
        key = ((r.get("recipient") or "").strip(), (r.get("action_name") or "").strip())
        st = (r.get("status") or "").strip()
        if st == "delivered":
            delivered_pairs.add(key)
        elif st == "opened":
            opened_pairs.add(key)
        elif st == "clicked":
            clicked_pairs.add(key)

    by_status_stream = defaultdict(Counter)
    for r in rows:
        stream = (r.get("c_stream_id") or "").strip() or "(none)"
        by_status_stream[stream][(r.get("status") or "").strip() or "(blank)"] += 1

    open_rate = None
    click_rate = None
    if delivered_pairs:
        open_rate = round(100 * len(opened_pairs) / len(delivered_pairs), 1)
        click_rate = round(100 * len(clicked_pairs) / len(delivered_pairs), 1)

    return {
        "filename": filename,
        "row_count": len(rows),
        "column_count": len(fields),
        "columns": fields,
        "date_range": {
            "earliest": min(timestamps) if timestamps else None,
            "latest": max(timestamps) if timestamps else None,
        },
        "campaign": campaign,
        "status": [{"name": k, "count": v} for k, v in status.most_common()],
        "streams": [{"name": k, "count": v} for k, v in sorted(streams.items())],
        "types": [{"name": k, "count": v} for k, v in types.most_common(15)],
        "recipients": {
            "unique_count": len(recipients),
            "top": [{"email": e, "count": c} for e, c in recipients.most_common(15)],
        },
        "templates": {
            "unique_count": len(actions),
            "items": [{"name": n, "count": c} for n, c in sorted(actions.items())],
        },
        "engagement": {
            "delivered_pairs": len(delivered_pairs),
            "opened_pairs": len(opened_pairs),
            "clicked_pairs": len(clicked_pairs),
            "open_rate": open_rate,
            "click_rate": click_rate,
            "opened_events": status.get("opened", 0),
            "clicked_events": status.get("clicked", 0),
        },
        "errors_count": len(errors),
        "status_by_stream": [
            {
                "stream": s,
                "breakdown": [{"status": st, "count": c} for st, c in sorted(counts.items())],
            }
            for s, counts in sorted(by_status_stream.items())
        ],
    }
