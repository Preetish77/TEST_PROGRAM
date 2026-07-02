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


def order_to_send(c_order_id):
    match = re.search(r"EM(\d+)", c_order_id or "", re.I)
    if not match:
        return None
    number = int(match.group(1))
    return "Initial: SL" if number % 2 == 1 else "Echo: SL"


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
            raw = raw.decode("utf-8", errors="replace")
    elif not isinstance(raw, str):
        raw = str(raw)

    return _parse_ko_csv_text(raw)


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

    current_stream = ""
    current_creative = ""
    current_mlr = ""
    current_jn = ""
    current_keycode4 = ""
    records = []

    for row in rows[1:]:
        stream = get(row, "Stream Name")
        creative = get(row, "Creative Name")
        mlr = get(row, "MLR Number")
        jn = get(row, "WF Job Number (Billcode)")
        send = get(row, "Send")
        subject = get(row, "Subject Lines + Preheaders")
        personalization = get(row, "Personalization")
        keycode4 = get(row, "Keycode 4")

        if stream:
            current_stream = stream
        if creative:
            current_creative = creative.replace("\n", " ").strip()
        if mlr:
            current_mlr = mlr
        if jn:
            current_jn = jn
            current_keycode4 = ""
        if keycode4:
            current_keycode4 = keycode4.lower()

        if send not in KO_SEND_SL or not subject:
            continue
        if not current_jn:
            continue

        records.append(
            {
                "stream_name": current_stream,
                "creative_name": current_creative,
                "mlr_number": current_mlr,
                "jn": current_jn,
                "send": send,
                "subject": subject,
                "subject_normalized": normalize_sl(subject),
                "personalization": personalization,
                "keycode4": current_keycode4,
                "has_nametoken": "[INS1]" in subject.upper() or personalization.lower() == "yes",
            }
        )

    return records


def validate_export_against_ko(export_rows, ko_rows):
    """Compare export SL + Keycode4 values to KO document (strict on special characters)."""
    ko_by_jn_send_key = {}
    for row in ko_rows:
        ko_by_jn_send_key[(row["jn"], row["send"], row["keycode4"])] = row

    ko_index = {}
    for row in ko_rows:
        key = (row["jn"], row["send"], row["keycode4"], row["subject_normalized"])
        ko_index[key] = row

    export_index = {}
    for row in export_rows:
        key = (row["jn"], row["send"], row["keycode4"], row["subject_normalized"])
        export_index[key] = row

    matched = []
    mismatches = []
    export_only = []
    ko_only = []
    seen_mismatch_keys = set()

    for key, export_row in export_index.items():
        if key in ko_index:
            ko_row = ko_index[key]
            matched.append(
                {
                    "jn": export_row["jn"],
                    "send": export_row["send"],
                    "keycode4": export_row["keycode4"],
                    "export_subject": export_row["subject"],
                    "ko_subject": ko_row["subject"],
                    "status": "Match",
                }
            )
        else:
            ko_row = ko_by_jn_send_key.get((key[0], key[1], key[2]))
            if ko_row:
                status = classify_subject_status(export_row["subject"], ko_row["subject"])
                mismatches.append(
                    {
                        "jn": export_row["jn"],
                        "send": export_row["send"],
                        "keycode4": export_row["keycode4"],
                        "export_subject": export_row["subject"],
                        "ko_subject": ko_row["subject"],
                        "status": status,
                    }
                )
                seen_mismatch_keys.add((key[0], key[1], key[2]))
            else:
                export_only.append(
                    {
                        "jn": export_row["jn"],
                        "send": export_row["send"],
                        "keycode4": export_row["keycode4"],
                        "export_subject": export_row["subject"],
                        "ko_subject": "",
                        "status": "Not in KO doc",
                    }
                )

    for key, ko_row in ko_index.items():
        if key not in export_index:
            if (key[0], key[1], key[2]) in seen_mismatch_keys:
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


def build_validation_csv(validation):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Status", "JN", "Send", "Keycode 4", "Export Subject", "KO Subject"])
    for group in ("matched", "mismatches", "export_only", "ko_only"):
        for row in validation[group]:
            writer.writerow(
                [
                    row["status"],
                    row["jn"],
                    row["send"],
                    row["keycode4"],
                    row["export_subject"],
                    row["ko_subject"],
                ]
            )
    return buf.getvalue()
