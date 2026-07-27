"""Synthetic test: stream5 removed from export but present in KO doc."""
from analyzer import validate_export_keycode4


def make_ko_rows(stream_creatives):
    rows = []
    for stream, creative in stream_creatives:
        keycode4 = f"{stream}|{creative}"
        for send in ("Initial: SL", "Echo: SL"):
            rows.append(
                {
                    "jn": "12345-6789",
                    "send": send,
                    "keycode4": keycode4,
                    "subject": f"Subject {stream}",
                    "subject_normalized": f"subject {stream}",
                }
            )
    return rows


def make_export_row(stream_num, creative):
    return {
        "status": "delivered",
        "c_job_number": "12345-6789",
        "c_stream_id": f"S0{stream_num}",
        "c_creative_id": creative,
        "c_order_id": "EM01",
        "campaign_name": "Test Campaign",
        "timestamp": "2026-01-15 10:00:00",
        "subject": f"Subject {stream_num}",
    }


def test_stream5_missing_from_export():
    ko_rows = make_ko_rows(
        [
            ("stream1", "creativea"),
            ("stream2", "creativeb"),
            ("stream3", "creativec"),
            ("stream4", "creatived"),
            ("stream5", "creativee"),
        ]
    )
    export_rows = [
        make_export_row(1, "creativea"),
        make_export_row(2, "creativeb"),
        make_export_row(3, "creativec"),
        make_export_row(4, "creatived"),
    ]

    result = validate_export_keycode4(export_rows, ko_rows=ko_rows, delivered_only=True)

    assert result["match_count"] == 4, f"expected 4 OK, got {result['match_count']}"
    assert result["missing_in_export_count"] == 1, (
        f"expected 1 missing stream5, got {result['missing_in_export_count']}"
    )
    missing = result["missing_in_export"]
    assert len(missing) == 1
    assert missing[0]["status"] == "Missing in export"
    assert missing[0]["keycode4"] == "stream5|creativee"
    assert missing[0]["c_stream_id"] == "S05"
    assert missing[0]["c_creative_id"] == "creativee"
    assert result["mismatch_count"] == 0
    assert result["export_only_count"] == 0

    print("PASS: stream5 missing from export is flagged in keycode4 validation")
    for row in result["rows"]:
        print(f"  {row['c_stream_id']:4} {row['c_creative_id']:12} {row['status']}")


def test_export_only_stream():
    ko_rows = make_ko_rows(
        [
            ("stream1", "creativea"),
            ("stream2", "creativeb"),
            ("stream3", "creativec"),
            ("stream4", "creatived"),
            ("stream5", "creativee"),
        ]
    )
    export_rows = [
        make_export_row(1, "creativea"),
        make_export_row(2, "creativeb"),
        make_export_row(3, "creativec"),
        make_export_row(4, "creatived"),
        make_export_row(5, "creativee"),
        {
            "status": "delivered",
            "c_job_number": "12345-6789",
            "c_stream_id": "S06",
            "c_creative_id": "extra",
            "c_order_id": "EM01",
            "campaign_name": "Test Campaign",
            "timestamp": "2026-01-15 10:00:00",
            "subject": "Extra",
        },
    ]

    result = validate_export_keycode4(export_rows, ko_rows=ko_rows, delivered_only=True)
    assert result["export_only_count"] == 1
    export_only = [r for r in result["rows"] if r["status"] == "Not in KO doc"]
    assert export_only[0]["c_stream_id"] == "S06"
    print("PASS: export-only stream6 flagged as Not in KO doc")


if __name__ == "__main__":
    test_stream5_missing_from_export()
    test_export_only_stream()
    print("\nAll keycode4 KO comparison tests passed.")
