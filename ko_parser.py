import csv
import io
import re

try:
    import openpyxl
except ImportError:
    openpyxl = None

KO_SEND_SL = ("Initial: SL", "Echo: SL")
INS1_PATTERN = re.compile(r"\[INS1\]", re.I)
NAMETOKEN_PATTERN = re.compile(r"\(\(\s*nametoken\s*\)\)", re.I)

KO_COLUMNS = [
    "Stream Name",
    "Creative Name",
    "MLR Number",
    "WF Job Number (Billcode)",
    "Send",
    "Subject Lines + Preheaders",
    "Personalization",
    "Keycode 4",
]


def decode_csv_bytes(raw):
    """Decode CSV bytes using the best-fit encoding (Excel often saves as cp1252, not UTF-8)."""
    if not isinstance(raw, bytes):
        return raw if isinstance(raw, str) else str(raw)

    if raw.startswith(b"\xff\xfe"):
        return raw.decode("utf-16-le")
    if raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16-be")

    best_text = None
    best_replacements = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        replacements = text.count("\ufffd")
        if best_replacements is None or replacements < best_replacements:
            best_replacements = replacements
            best_text = text

    return best_text if best_text is not None else raw.decode("utf-8", errors="replace")


def normalize_sl(text):
    """Normalize subject lines for strict comparison (nametoken/case/whitespace only)."""
    value = (text or "").strip()
    value = NAMETOKEN_PATTERN.sub("[INS1]", value)
    value = INS1_PATTERN.sub("[INS1]", value)
    value = value.replace("\u2019", "'").replace("\u2018", "'")
    value = re.sub(r"\s+", " ", value)
    return value.casefold()


def normalize_sl_loose(text):
    """Loose normalization for detecting encoding-only differences (dash/? variants)."""
    value = normalize_sl(text)
    dash_chars = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
    value = re.sub(f"[{re.escape(dash_chars)}]", "-", value)
    while re.search(r"(\w)\?(\w)", value):
        value = re.sub(r"(\w)\?(\w)", r"\1-\2", value)
    value = value.replace("\ufffd", "-")
    return value


def classify_subject_status(export_subject, ko_subject):
    """Return Match, Special character mismatch, or Subject mismatch."""
    if normalize_sl(export_subject) == normalize_sl(ko_subject):
        return "Match"
    if normalize_sl_loose(export_subject) == normalize_sl_loose(ko_subject):
        return "Special character mismatch"
    return "Subject mismatch"


def stream_id_to_keycode_stream(c_stream_id):
    match = re.match(r"S0?(\d+)", (c_stream_id or "").strip(), re.I)
    if match:
        return f"stream{int(match.group(1))}"
    return None


def build_keycode4(c_stream_id, c_creative_id):
    stream = stream_id_to_keycode_stream(c_stream_id)
    creative = (c_creative_id or "").strip().lower()
    if stream and creative:
        return f"{stream}|{creative}"
    return None


def parse_em_number(c_order_id):
    """Extract EM sequence number from c_order_id (e.g. EM03 -> 3)."""
    match = re.search(r"EM(\d+)", c_order_id or "", re.I)
    return int(match.group(1)) if match else None


def em_num_to_creative_idx(em_num):
    """Map EM number to creative block index: EM01/02 -> 0, EM03/04 -> 1, etc."""
    if em_num is None or em_num < 1:
        return None
    return (em_num - 1) // 2


def order_to_send(c_order_id):
    em_num = parse_em_number(c_order_id)
    if em_num is None:
        return None
    return "Initial: SL" if em_num % 2 == 1 else "Echo: SL"


def export_sl_display(subject, has_nametoken):
    """Format export subject the way KO expects in output."""
    text = (subject or "").strip()
    if has_nametoken:
        text = NAMETOKEN_PATTERN.sub("", text).strip()
        return f"[INS1] {text}".strip()
    return text


def _find_creative_details_sheet(workbook):
    for name in workbook.sheetnames:
        lower = name.lower().replace("_", " ")
        if "creative" in lower and "detail" in lower:
            return workbook[name]
    for name in workbook.sheetnames:
        if "creative" in name.lower():
            return workbook[name]
    return None


def _xlsx_to_ko_csv_text(file_bytes):
    """Read Creative Details tab from KO xlsx and return CSV text for parsing."""
    if openpyxl is None:
        raise ImportError("openpyxl required for .xlsx KO files. Run: py -3 -m pip install openpyxl")

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheet = _find_creative_details_sheet(wb)
    if sheet is None:
        names = ", ".join(wb.sheetnames)
        wb.close()
        raise ValueError(f"Creative Details tab not found. Sheets: {names}")

    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in sheet.iter_rows(values_only=True):
        writer.writerow(["" if v is None else str(v).strip() for v in row])
    wb.close()
    return buf.getvalue()


def parse_ko_document(file_obj):
    """Parse KO Creative Details from .xlsx or .csv."""
    if hasattr(file_obj, "read"):
        raw = file_obj.read()
    else:
        raw = file_obj

    if isinstance(raw, bytes):
        if raw[:2] == b"PK":
            raw = _xlsx_to_ko_csv_text(raw)
        else:
            raw = decode_csv_bytes(raw)
    elif not isinstance(raw, str):
        raw = str(raw)

    return _parse_ko_csv_text(raw)


def _flush_ko_block(block, records, ctx):
    """Emit SL records from a parsed creative block."""
    if not block:
        return
    jn = block.get("jn", "")
    keycode4 = block.get("keycode4", "")
    if not jn or not keycode4:
        return
    for entry in block.get("sl_entries", []):
        subject = entry["subject"]
        personalization = entry.get("personalization", "")
        records.append(
            {
                "stream_name": ctx["stream"],
                "creative_name": ctx["creative"],
                "mlr_number": ctx["mlr"],
                "jn": jn,
                "send": entry["send"],
                "subject": subject,
                "subject_normalized": normalize_sl(subject),
                "personalization": personalization,
                "keycode4": keycode4,
                "has_nametoken": "[INS1]" in subject.upper() or personalization.lower() == "yes",
            }
        )


def _parse_ko_csv_text(raw):
    """Parse KO creative-details CSV into SL rows."""
    reader = csv.reader(io.StringIO(raw))
    rows = list(reader)
    if not rows:
        return []

    header = rows[0]
    col_index = {name.strip(): idx for idx, name in enumerate(header)}

    def get(row, name, default=""):
        idx = col_index.get(name)
        if idx is None or idx >= len(row):
            return default
        return (row[idx] or "").strip()

    ctx = {"stream": "", "creative": "", "mlr": ""}
    current_block = None
    pending_jn = ""
    records = []

    for row in rows[1:]:
        stream = get(row, "Stream Name")
        creative = get(row, "Creative Name")
        mlr = get(row, "MLR Number")
        jn = get(row, "WF Job Number (Billcode)")
        send = get(row, "Send")
        subject = get(row, "Subject Lines + Preheaders")
        personalization = get(row, "Personalization")
        keycode4 = get(row, "Keycode 4").strip().lower()

        if stream:
            ctx["stream"] = stream
        if creative:
            ctx["creative"] = creative.replace("\n", " ").strip()
        if mlr:
            ctx["mlr"] = mlr

        # New creative block starts on Initial: SL with Keycode 4.
        if send == "Initial: SL" and keycode4:
            _flush_ko_block(current_block, records, ctx)
            current_block = {
                "jn": jn or pending_jn,
                "keycode4": keycode4,
                "sl_entries": [],
            }
            pending_jn = ""
        elif jn:
            if current_block is not None:
                current_block["jn"] = jn
            else:
                pending_jn = jn

        if send in KO_SEND_SL and subject and current_block is not None:
            current_block["sl_entries"].append(
                {
                    "send": send,
                    "subject": subject,
                    "personalization": personalization,
                }
            )

    _flush_ko_block(current_block, records, ctx)
    return records


def keycode4_creative(keycode4):
    """Return the creative segment after stream| in Keycode 4."""
    parts = (keycode4 or "").split("|", 1)
    return parts[1] if len(parts) == 2 else (keycode4 or "")


def build_ko_stream_em_index(ko_rows):
    """
    Index KO SL rows by (stream, em_num) following Creative Details block order.
    Within each stream: EM01=1st creative Initial, EM02=1st creative Echo, EM03=2nd Initial, etc.
    Also builds fallback index by (creative, send, subject_normalized).
    """
    stream_creative_order = {}
    stream_creative_rows = {}

    for row in ko_rows:
        keycode4 = (row.get("keycode4") or "").strip().lower()
        parts = keycode4.split("|", 1)
        if len(parts) != 2:
            continue
        stream, creative = parts[0].strip(), parts[1].strip()
        if stream not in stream_creative_order:
            stream_creative_order[stream] = []
        if creative not in stream_creative_order[stream]:
            stream_creative_order[stream].append(creative)
        stream_creative_rows.setdefault((stream, creative), {})[row["send"]] = row

    by_stream_em = {}
    by_creative_send_subject = {}
    ko_row_em = {}

    for stream, creatives in stream_creative_order.items():
        em_num = 1
        for creative in creatives:
            rows_for_creative = stream_creative_rows.get((stream, creative), {})
            for send in KO_SEND_SL:
                ko_row = rows_for_creative.get(send)
                if ko_row is None:
                    continue
                by_stream_em[(stream, em_num)] = ko_row
                ko_row_em[id(ko_row)] = em_num
                sk = (creative, send, ko_row["subject_normalized"])
                by_creative_send_subject.setdefault(sk, []).append(ko_row)
                em_num += 1

    return by_stream_em, by_creative_send_subject, ko_row_em


def _match_status_label(export_row, ko_row):
    """Return Match / Special character mismatch / Subject mismatch (SL-focused)."""
    return classify_subject_status(export_row["subject"], ko_row["subject"])


def _match_record(export_row, ko_row, status):
    record = {
        "jn": export_row["jn"],
        "send": export_row["send"],
        "keycode4": export_row["keycode4"],
        "export_subject": export_row["subject"],
        "ko_subject": ko_row["subject"],
        "status": status,
        "c_stream_id": export_row.get("c_stream_id", ""),
        "c_order_id": export_row.get("c_order_id", ""),
        "c_creative_id": export_row.get("c_creative_id", ""),
        "em_num": export_row.get("em_num"),
    }
    if ko_row["jn"] != export_row["jn"]:
        record["ko_jn"] = ko_row["jn"]
    if ko_row["keycode4"] != export_row["keycode4"]:
        record["ko_keycode4"] = ko_row["keycode4"]
    ko_stream = (ko_row.get("keycode4") or "").split("|")[0]
    export_stream = stream_id_to_keycode_stream(export_row.get("c_stream_id"))
    if ko_stream and export_stream and ko_stream != export_stream:
        record["ko_stream"] = ko_stream
    return record


def validate_export_against_ko(export_rows, ko_rows):
    """
    Compare export SL rows to KO document using stream + EM order + creative + subject.
    Primary key: (stream from c_stream_id, EM number). Fallback: creative + send + subject
    when test export uses different stream numbers than production KO.
    """
    by_stream_em, by_creative_send_subject, ko_row_em = build_ko_stream_em_index(ko_rows)

    matched = []
    mismatches = []
    export_only = []
    ko_only = []
    matched_ko_keys = set()
    matched_ko_css_keys = set()
    seen_mismatch_keys = set()

    for export_row in export_rows:
        export_stream = stream_id_to_keycode_stream(export_row.get("c_stream_id"))
        em_num = export_row.get("em_num")
        if em_num is None:
            em_num = parse_em_number(export_row.get("c_order_id"))

        creative = (export_row.get("c_creative_id") or keycode4_creative(export_row.get("keycode4"))).strip().lower()
        send = export_row["send"]
        subject_norm = export_row["subject_normalized"]

        ko_row = None
        stream_aligned = False
        em_aligned = False

        if export_stream and em_num:
            ko_row = by_stream_em.get((export_stream, em_num))
            if ko_row:
                stream_aligned = True
                em_aligned = True
                ko_creative = keycode4_creative(ko_row["keycode4"])
                if ko_creative != creative:
                    ko_row = None

        if ko_row is None:
            css_key = (creative, send, subject_norm)
            candidates = by_creative_send_subject.get(css_key, [])
            if candidates:
                ko_row = candidates[0]
                ko_stream = (ko_row.get("keycode4") or "").split("|")[0]
                stream_aligned = export_stream == ko_stream
                ko_em = ko_row_em.get(id(ko_row))
                em_aligned = em_num == ko_em if em_num and ko_em else False

        if ko_row is None:
            export_only.append(
                {
                    "jn": export_row["jn"],
                    "send": export_row["send"],
                    "keycode4": export_row["keycode4"],
                    "export_subject": export_row["subject"],
                    "ko_subject": "",
                    "status": "Not in KO doc",
                    "c_stream_id": export_row.get("c_stream_id", ""),
                    "c_order_id": export_row.get("c_order_id", ""),
                    "c_creative_id": export_row.get("c_creative_id", ""),
                    "em_num": em_num,
                }
            )
            continue

        status = _match_status_label(export_row, ko_row)
        record = _match_record(export_row, ko_row, status)

        if status == "Match" or status.startswith("Match ("):
            matched.append(record)
            matched_ko_keys.add((ko_row["jn"], ko_row["send"], ko_row["keycode4"], ko_row["subject_normalized"]))
            matched_ko_css_keys.add((creative, send, subject_norm))
        else:
            mismatches.append(record)
            seen_mismatch_keys.add((export_row["jn"], export_row["send"], export_row["keycode4"]))

    for ko_row in ko_rows:
        exact_key = (ko_row["jn"], ko_row["send"], ko_row["keycode4"], ko_row["subject_normalized"])
        if exact_key in matched_ko_keys:
            continue
        css_key = (keycode4_creative(ko_row["keycode4"]), ko_row["send"], ko_row["subject_normalized"])
        if css_key in matched_ko_css_keys:
            continue
        if (ko_row["jn"], ko_row["send"], ko_row["keycode4"]) in seen_mismatch_keys:
            continue
        ko_only.append(
            {
                "jn": ko_row["jn"],
                "send": ko_row["send"],
                "keycode4": ko_row["keycode4"],
                "export_subject": "",
                "ko_subject": ko_row["subject"],
                "status": "Missing from export",
            }
        )

    return {
        "matched": matched,
        "mismatches": mismatches,
        "export_only": export_only,
        "ko_only": ko_only,
        "match_count": len(matched),
        "mismatch_count": len(mismatches),
        "export_only_count": len(export_only),
        "ko_only_count": len(ko_only),
    }


def build_ko_aligned_csv(export_rows):
    """Build CSV aligned to KO document SL columns."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(KO_COLUMNS)
    last_jn = None
    for row in export_rows:
        include_header_fields = row["jn"] != last_jn
        writer.writerow(
            [
                "" if not include_header_fields else f"Stream from export ({row['c_stream_id']})",
                "" if not include_header_fields else row.get("action_name", ""),
                "NA",
                row["jn"] if include_header_fields else "",
                row["send"],
                row["subject_ko_format"],
                row["personalization"],
                row["keycode4"],
            ]
        )
        last_jn = row["jn"]
    return buf.getvalue()


def build_validation_csv(validation, export_label="Subject (Campaign Export)", ko_label="Subject (KO Creative Details doc)"):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Status",
            "Stream",
            "EM Order",
            "c_creative_id",
            "JN",
            "Send",
            "Keycode 4",
            export_label,
            ko_label,
            "KO JN",
            "KO Keycode 4",
        ]
    )
    for group in ("matched", "mismatches", "export_only", "ko_only"):
        for row in validation[group]:
            writer.writerow(
                [
                    row["status"],
                    row.get("c_stream_id", ""),
                    row.get("c_order_id", ""),
                    row.get("c_creative_id", ""),
                    row["jn"],
                    row["send"],
                    row["keycode4"],
                    row["export_subject"],
                    row["ko_subject"],
                    row.get("ko_jn", ""),
                    row.get("ko_keycode4", ""),
                ]
            )
    return buf.getvalue()
