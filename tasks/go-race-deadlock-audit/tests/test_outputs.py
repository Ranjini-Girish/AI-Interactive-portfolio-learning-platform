# scaffold-status: oracle-pending
"""Behavioral tests
 for the yard appointment audit CLI."""

from __future__ import annotations

import json
import subprocess
import os
from pathlib import Path


STATUS_KEYS = {
    "ready": 0,
    "blocked": 0,
    "stale": 0,
    "overbooked": 0,
    "unknown_appointment": 0,
}


def run_yardcheck(
    manifest: Path,
    appointments: Path,
    events: Path,
    output: Path,
) -> dict:
    """Run the CLI and return the parsed report JSON."""
    result = subprocess.run(
        [
            "go",
            "run",
            "./cmd/yardcheck",
            "--manifest",
            str(manifest),
            "--appointments",
            str(appointments),
            "--events",
            str(events),
            "--out",
            str(output),
        ],
        cwd="/app",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.exists(), "yardcheck did not create the requested output file"
    return json.loads(output.read_text())


def by_container(report: dict) -> dict:
    """Index report entries by container id for readable assertions."""
    return {entry["container_id"]: entry for entry in report["containers"]}


def by_booking(report: dict) -> dict:
    """Index booking summary entries by booking id for readable assertions."""
    return {entry["booking"]: entry for entry in report["bookings"]}


def by_carrier(report: dict) -> dict:
    """Index carrier summary entries by carrier for readable assertions."""
    return {entry["carrier"]: entry for entry in report["carrier_summary"]}


def counts(**overrides: int) -> dict:
    """Return a full status-count mapping with omitted values set to zero."""
    status_counts = dict(STATUS_KEYS)
    status_counts.update(overrides)
    return status_counts


def test_default_fixture_applies_all_status_rules(tmp_path: Path) -> None:
    """Bundled data should exercise timezone, cutoff, temperature, and booking logic."""
    report = run_yardcheck(
        Path(os.environ.get("GRD_APP_DATA_MANIFEST_CSV", "/app/data/manifest.csv")),
        Path(os.environ.get("GRD_APP_DATA_APPOINTMENTS_CSV", "/app/data/appointments.csv")),
        Path(os.environ.get("GRD_APP_DATA_EVENTS_NDJSON", "/app/data/events.ndjson")),
        tmp_path / "yard_report.json",
    )

    assert report["generated_at"] == "2026-07-14T22:50:00Z"
    assert report["summary"] == {
        "ready": 1,
        "blocked": 1,
        "stale": 3,
        "overbooked": 3,
        "unknown_appointment": 1,
    }
    assert [entry["container_id"] for entry in report["containers"]] == sorted(
        entry["container_id"] for entry in report["containers"]
    )
    assert [entry["booking"] for entry in report["bookings"]] == sorted(
        entry["booking"] for entry in report["bookings"]
    )
    assert [entry["carrier"] for entry in report["carrier_summary"]] == sorted(
        entry["carrier"] for entry in report["carrier_summary"]
    )
    assert [
        (entry["status"], entry["container_id"]) for entry in report["exceptions"]
    ] == [
        ("blocked", "MATU2002002"),
        ("overbooked", "FSCU1001001"),
        ("overbooked", "FSCU1001002"),
        ("overbooked", "FSCU1001003"),
        ("stale", "CUT6006001"),
        ("stale", "HLCU4004001"),
        ("stale", "OOCU3003001"),
        ("unknown_appointment", "MISS5005001"),
    ]

    entries = by_container(report)
    assert entries["CUT6006001"]["carrier"] == "HarborLine"
    assert entries["CUT6006001"]["status"] == "stale"
    assert entries["CUT6006001"]["reason_codes"] == ["CARRIER_CUTOFF_MISSED"]
    assert entries["CUT6006001"]["last_event_utc"] == "2026-07-14T22:50:00Z"
    assert entries["FSCU1001001"]["booking"] == "BK-101"
    assert entries["FSCU1001001"]["carrier"] == "Orbit"
    assert entries["FSCU1001001"]["status"] == "overbooked"
    assert entries["FSCU1001001"]["reason_codes"] == ["CAPACITY_EXCEEDED"]
    assert entries["FSCU1001002"]["last_event_type"] == "release"
    assert entries["FSCU1001002"]["last_event_utc"] == "2026-07-14T16:30:00Z"
    assert entries["MATU2002001"]["status"] == "ready"
    assert entries["MATU2002001"]["reason_codes"] == []
    assert entries["MATU2002002"]["status"] == "blocked"
    assert entries["MATU2002002"]["reason_codes"] == ["ACTIVE_HOLD"]
    assert entries["OOCU3003001"]["status"] == "stale"
    assert entries["OOCU3003001"]["reason_codes"] == ["OUTSIDE_WINDOW"]
    assert entries["HLCU4004001"]["status"] == "stale"
    assert entries["HLCU4004001"]["reason_codes"] == ["NO_GATE_IN"]
    assert entries["HLCU4004001"]["appointment_window_utc"] == [
        "2026-07-14T22:00:00Z",
        "2026-07-15T00:00:00Z",
    ]
    assert entries["MISS5005001"]["status"] == "unknown_appointment"
    assert entries["MISS5005001"]["reason_codes"] == ["NO_APPOINTMENT"]
    assert entries["MISS5005001"]["appointment_window_utc"] == []

    bookings = by_booking(report)
    assert bookings["BK-101"] == {
        "booking": "BK-101",
        "capacity": 2,
        "appointment_window_utc": [
            "2026-07-14T15:00:00Z",
            "2026-07-14T17:00:00Z",
        ],
        "container_ids": ["FSCU1001001", "FSCU1001002", "FSCU1001003"],
        "carriers": ["Orbit"],
        "status_counts": counts(overbooked=3),
    }
    assert bookings["BK-202"]["container_ids"] == ["MATU2002001", "MATU2002002"]
    assert bookings["BK-202"]["carriers"] == ["Northstar"]
    assert bookings["BK-202"]["status_counts"] == counts(ready=1, blocked=1)
    assert bookings["BK-303"]["status_counts"] == counts(stale=1)
    assert bookings["BK-404"] == {
        "booking": "BK-404",
        "capacity": 2,
        "appointment_window_utc": [
            "2026-07-14T22:00:00Z",
            "2026-07-15T00:00:00Z",
        ],
        "container_ids": ["CUT6006001", "HLCU4004001"],
        "carriers": ["HarborLine"],
        "status_counts": counts(stale=2),
    }
    assert bookings["BK-999"] == {
        "booking": "BK-999",
        "capacity": 0,
        "appointment_window_utc": [],
        "container_ids": ["MISS5005001"],
        "carriers": ["DrayNow"],
        "status_counts": counts(unknown_appointment=1),
    }

    carriers = by_carrier(report)
    assert carriers["BluePier"] == {
        "carrier": "BluePier",
        "booking_ids": ["BK-303"],
        "container_ids": ["OOCU3003001"],
        "requires_temp_check": 0,
        "status_counts": counts(stale=1),
    }
    assert carriers["DrayNow"]["status_counts"] == counts(unknown_appointment=1)
    assert carriers["HarborLine"] == {
        "carrier": "HarborLine",
        "booking_ids": ["BK-404"],
        "container_ids": ["CUT6006001", "HLCU4004001"],
        "requires_temp_check": 0,
        "status_counts": counts(stale=2),
    }
    assert carriers["Northstar"] == {
        "carrier": "Northstar",
        "booking_ids": ["BK-202"],
        "container_ids": ["MATU2002001", "MATU2002002"],
        "requires_temp_check": 2,
        "status_counts": counts(ready=1, blocked=1),
    }
    assert carriers["Orbit"] == {
        "carrier": "Orbit",
        "booking_ids": ["BK-101"],
        "container_ids": ["FSCU1001001", "FSCU1001002", "FSCU1001003"],
        "requires_temp_check": 0,
        "status_counts": counts(overbooked=3),
    }

    exception_by_id = {entry["container_id"]: entry for entry in report["exceptions"]}
    assert exception_by_id["MATU2002002"] == {
        "container_id": "MATU2002002",
        "booking": "BK-202",
        "carrier": "Northstar",
        "status": "blocked",
        "primary_reason": "ACTIVE_HOLD",
        "last_event_utc": "2026-07-14T16:30:00Z",
        "minutes_from_window_start": 20,
    }
    assert exception_by_id["CUT6006001"]["minutes_from_window_start"] == 50
    assert exception_by_id["HLCU4004001"]["primary_reason"] == "NO_GATE_IN"
    assert exception_by_id["HLCU4004001"]["minutes_from_window_start"] is None
    assert exception_by_id["MISS5005001"]["primary_reason"] == "NO_APPOINTMENT"
    assert exception_by_id["MISS5005001"]["minutes_from_window_start"] is None


def test_timezone_capacity_cutoffs_and_service_readiness(tmp_path: Path) -> None:
    """Temporary fixtures catch layered rules that are not visible in the default data."""
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "\n".join(
            [
                "container_id,booking,carrier,requires_temp_check",
                "TCLU1111111,BK-TYO,K Line,true",
                "TCLU1111112,BK-TYO,K Line,false",
                "LONU2222222,BK-LON,Maersk,false",
                "BNDY4444444,BK-UTC,Hapag,false",
                "BNDY5555555,BK-UTC,Hapag,false",
                "MULT6666666,BK-UTC,Hapag,false",
                "MULT7777777,BK-UTC,Hapag,false",
                "NOEV8888888,BK-UTC,Hapag,false",
                "POST1010101,BK-UTC,Hapag,true",
                "REEF9999999,BK-UTC,Hapag,true",
                "LATE1231231,BK-UTC,Hapag,false",
                "UNKN3333333,BK-MISSING,Ghost,false",
                "UNKN4444444,BK-MISSING,Ghost,true",
                "",
            ]
        )
    )
    appointments = tmp_path / "appointments.csv"
    appointments.write_text(
        "\n".join(
            [
                "booking,window_start_local,window_end_local,timezone,capacity,carrier_cutoff_min",
                "BK-TYO,2026-02-03 09:00,2026-02-03 10:00,Asia/Tokyo,1,60",
                "BK-LON,2026-02-03 09:00,2026-02-03 10:00,Europe/London,1,60",
                "BK-UTC,2026-02-03 12:00,2026-02-03 13:00,UTC,5,45",
                "",
            ]
        )
    )
    events = tmp_path / "events.ndjson"
    events.write_text(
        "\n".join(
            [
                '{"container_id":"TCLU1111111","type":"temp_check","timestamp":"2026-02-03T00:00:00Z"}',
                '{"container_id":"TCLU1111111","type":"gate_in","timestamp":"2026-02-03T00:20:00Z"}',
                '{"container_id":"TCLU1111111","type":"hold","timestamp":"2026-02-03T00:30:00Z"}',
                '{"container_id":"TCLU1111111","type":"release","timestamp":"2026-02-03T00:40:00Z"}',
                '{"container_id":"TCLU1111111","type":"hold","timestamp":"2026-02-03T00:05:00Z"}',
                '{"container_id":"TCLU1111112","type":"gate_in","timestamp":"2026-02-03T00:10:00Z"}',
                '{"container_id":"LONU2222222","type":"gate_in","timestamp":"2026-02-03T09:15:00Z"}',
                '{"container_id":"LONU2222222","type":"hold","timestamp":"2026-02-03T09:45:00Z"}',
                '{"container_id":"LONU2222222","type":"release","timestamp":"2026-02-03T09:20:00Z"}',
                '{"container_id":"BNDY4444444","type":"gate_in","timestamp":"2026-02-03T12:00:00Z"}',
                '{"container_id":"BNDY4444444","type":"release","timestamp":"2026-02-03T12:10:00Z"}',
                '{"container_id":"BNDY5555555","type":"gate_in","timestamp":"2026-02-03T13:00:00Z"}',
                '{"container_id":"MULT6666666","type":"gate_in","timestamp":"2026-02-03T11:30:00Z"}',
                '{"container_id":"MULT6666666","type":"gate_in","timestamp":"2026-02-03T12:30:00Z"}',
                '{"container_id":"MULT6666666","type":"release","timestamp":"2026-02-03T12:35:00Z"}',
                '{"container_id":"MULT7777777","type":"gate_in","timestamp":"2026-02-03T12:20:00Z"}',
                '{"container_id":"MULT7777777","type":"gate_in","timestamp":"2026-02-03T13:05:00Z"}',
                '{"container_id":"POST1010101","type":"gate_in","timestamp":"2026-02-03T12:10:00Z"}',
                '{"container_id":"POST1010101","type":"temp_check","timestamp":"2026-02-03T12:30:00Z"}',
                '{"container_id":"REEF9999999","type":"temp_check","timestamp":"2026-02-03T05:00:00Z"}',
                '{"container_id":"REEF9999999","type":"gate_in","timestamp":"2026-02-03T12:20:00Z"}',
                '{"container_id":"LATE1231231","type":"gate_in","timestamp":"2026-02-03T12:50:00Z"}',
                '{"container_id":"UNKN3333333","type":"gate_in","timestamp":"2026-02-03T00:15:00Z"}',
                '{"container_id":"UNKN4444444","type":"hold","timestamp":"2026-02-03T00:30:00Z"}',
                "",
            ]
        )
    )

    report = run_yardcheck(manifest, appointments, events, tmp_path / "custom.json")
    assert report["generated_at"] == "2026-02-03T13:05:00Z"
    assert report["summary"] == {
        "ready": 2,
        "blocked": 3,
        "stale": 4,
        "overbooked": 2,
        "unknown_appointment": 2,
    }

    entries = by_container(report)
    assert entries["TCLU1111111"]["booking"] == "BK-TYO"
    assert entries["TCLU1111111"]["appointment_window_utc"] == [
        "2026-02-03T00:00:00Z",
        "2026-02-03T01:00:00Z",
    ]
    assert entries["TCLU1111111"]["status"] == "overbooked"
    assert entries["TCLU1111112"]["status"] == "overbooked"
    assert entries["LONU2222222"]["status"] == "blocked"
    assert entries["LONU2222222"]["reason_codes"] == ["ACTIVE_HOLD"]
    assert entries["LONU2222222"]["last_event_type"] == "hold"
    assert entries["LONU2222222"]["last_event_utc"] == "2026-02-03T09:45:00Z"
    assert entries["BNDY4444444"]["appointment_window_utc"] == [
        "2026-02-03T12:00:00Z",
        "2026-02-03T13:00:00Z",
    ]
    assert entries["BNDY4444444"]["status"] == "ready"
    assert entries["BNDY4444444"]["last_event_type"] == "release"
    assert entries["BNDY5555555"]["status"] == "stale"
    assert entries["BNDY5555555"]["reason_codes"] == ["OUTSIDE_WINDOW"]
    assert entries["MULT6666666"]["status"] == "ready"
    assert entries["MULT6666666"]["last_event_type"] == "release"
    assert entries["MULT6666666"]["last_event_utc"] == "2026-02-03T12:35:00Z"
    assert entries["MULT7777777"]["status"] == "stale"
    assert entries["MULT7777777"]["reason_codes"] == ["OUTSIDE_WINDOW"]
    assert entries["NOEV8888888"]["status"] == "stale"
    assert entries["NOEV8888888"]["reason_codes"] == ["NO_GATE_IN"]
    assert entries["NOEV8888888"]["last_event_type"] == ""
    assert entries["POST1010101"]["status"] == "blocked"
    assert entries["POST1010101"]["reason_codes"] == ["TEMP_CHECK_MISSING"]
    assert entries["POST1010101"]["last_event_type"] == "temp_check"
    assert entries["POST1010101"]["last_event_utc"] == "2026-02-03T12:30:00Z"
    assert entries["REEF9999999"]["status"] == "blocked"
    assert entries["REEF9999999"]["reason_codes"] == ["TEMP_CHECK_MISSING"]
    assert entries["LATE1231231"]["status"] == "stale"
    assert entries["LATE1231231"]["reason_codes"] == ["CARRIER_CUTOFF_MISSED"]
    assert entries["UNKN3333333"]["status"] == "unknown_appointment"
    assert entries["UNKN4444444"]["status"] == "unknown_appointment"
    assert entries["UNKN4444444"]["reason_codes"] == ["NO_APPOINTMENT"]
    assert entries["UNKN4444444"]["last_event_type"] == "hold"

    bookings = by_booking(report)
    assert bookings["BK-TYO"] == {
        "booking": "BK-TYO",
        "capacity": 1,
        "appointment_window_utc": [
            "2026-02-03T00:00:00Z",
            "2026-02-03T01:00:00Z",
        ],
        "container_ids": ["TCLU1111111", "TCLU1111112"],
        "carriers": ["K Line"],
        "status_counts": counts(overbooked=2),
    }
    assert bookings["BK-LON"]["status_counts"] == counts(blocked=1)
    assert bookings["BK-UTC"] == {
        "booking": "BK-UTC",
        "capacity": 5,
        "appointment_window_utc": [
            "2026-02-03T12:00:00Z",
            "2026-02-03T13:00:00Z",
        ],
        "container_ids": [
            "BNDY4444444",
            "BNDY5555555",
            "LATE1231231",
            "MULT6666666",
            "MULT7777777",
            "NOEV8888888",
            "POST1010101",
            "REEF9999999",
        ],
        "carriers": ["Hapag"],
        "status_counts": counts(ready=2, blocked=2, stale=4),
    }
    assert bookings["BK-MISSING"] == {
        "booking": "BK-MISSING",
        "capacity": 0,
        "appointment_window_utc": [],
        "container_ids": ["UNKN3333333", "UNKN4444444"],
        "carriers": ["Ghost"],
        "status_counts": counts(unknown_appointment=2),
    }

    carriers = by_carrier(report)
    assert carriers["Ghost"] == {
        "carrier": "Ghost",
        "booking_ids": ["BK-MISSING"],
        "container_ids": ["UNKN3333333", "UNKN4444444"],
        "requires_temp_check": 1,
        "status_counts": counts(unknown_appointment=2),
    }
    assert carriers["Hapag"] == {
        "carrier": "Hapag",
        "booking_ids": ["BK-UTC"],
        "container_ids": [
            "BNDY4444444",
            "BNDY5555555",
            "LATE1231231",
            "MULT6666666",
            "MULT7777777",
            "NOEV8888888",
            "POST1010101",
            "REEF9999999",
        ],
        "requires_temp_check": 2,
        "status_counts": counts(ready=2, blocked=2, stale=4),
    }
    assert carriers["K Line"]["requires_temp_check"] == 1
    assert carriers["K Line"]["status_counts"] == counts(overbooked=2)
    assert carriers["Maersk"]["status_counts"] == counts(blocked=1)

    assert [
        (entry["status"], entry["container_id"], entry["minutes_from_window_start"])
        for entry in report["exceptions"]
    ] == [
        ("blocked", "LONU2222222", 15),
        ("blocked", "POST1010101", 10),
        ("blocked", "REEF9999999", 20),
        ("overbooked", "TCLU1111111", 20),
        ("overbooked", "TCLU1111112", 10),
        ("stale", "BNDY5555555", 60),
        ("stale", "LATE1231231", 50),
        ("stale", "MULT7777777", 65),
        ("stale", "NOEV8888888", None),
        ("unknown_appointment", "UNKN3333333", None),
        ("unknown_appointment", "UNKN4444444", None),
    ]
    exception_by_id = {entry["container_id"]: entry for entry in report["exceptions"]}
    assert exception_by_id["POST1010101"]["primary_reason"] == "TEMP_CHECK_MISSING"
    assert exception_by_id["REEF9999999"]["primary_reason"] == "TEMP_CHECK_MISSING"
    assert exception_by_id["MULT7777777"]["primary_reason"] == "OUTSIDE_WINDOW"
    assert exception_by_id["UNKN4444444"]["last_event_utc"] == "2026-02-03T00:30:00Z"


def test_equal_timestamp_events_use_file_order(tmp_path: Path) -> None:
    """Events tied on timestamp should use later file lines as the later event."""
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "\n".join(
            [
                "container_id,booking,carrier,requires_temp_check",
                "TIEHOLD0001,BK-TIE,Union,false",
                "TIEDISP0002,BK-TIE,Union,false",
                "",
            ]
        )
    )
    appointments = tmp_path / "appointments.csv"
    appointments.write_text(
        "\n".join(
            [
                "booking,window_start_local,window_end_local,timezone,capacity,carrier_cutoff_min",
                "BK-TIE,2026-03-05 12:00,2026-03-05 13:00,UTC,2,60",
                "",
            ]
        )
    )
    events = tmp_path / "events.ndjson"
    events.write_text(
        "\n".join(
            [
                '{"container_id":"TIEHOLD0001","type":"gate_in","timestamp":"2026-03-05T12:05:00Z"}',
                '{"container_id":"TIEHOLD0001","type":"release","timestamp":"2026-03-05T12:10:00Z"}',
                '{"container_id":"TIEHOLD0001","type":"hold","timestamp":"2026-03-05T12:10:00Z"}',
                '{"container_id":"TIEDISP0002","type":"gate_in","timestamp":"2026-03-05T12:20:00Z"}',
                '{"container_id":"TIEDISP0002","type":"inspect","timestamp":"2026-03-05T12:25:00Z"}',
                '{"container_id":"TIEDISP0002","type":"release","timestamp":"2026-03-05T12:25:00Z"}',
                "",
            ]
        )
    )

    report = run_yardcheck(manifest, appointments, events, tmp_path / "ties.json")
    assert report["generated_at"] == "2026-03-05T12:25:00Z"
    assert report["summary"] == counts(ready=1, blocked=1)

    entries = by_container(report)
    assert entries["TIEHOLD0001"]["status"] == "blocked"
    assert entries["TIEHOLD0001"]["reason_codes"] == ["ACTIVE_HOLD"]
    assert entries["TIEHOLD0001"]["last_event_type"] == "hold"
    assert entries["TIEHOLD0001"]["last_event_utc"] == "2026-03-05T12:10:00Z"
    assert entries["TIEDISP0002"]["status"] == "ready"
    assert entries["TIEDISP0002"]["last_event_type"] == "release"
    assert entries["TIEDISP0002"]["last_event_utc"] == "2026-03-05T12:25:00Z"

    bookings = by_booking(report)
    assert bookings["BK-TIE"] == {
        "booking": "BK-TIE",
        "capacity": 2,
        "appointment_window_utc": [
            "2026-03-05T12:00:00Z",
            "2026-03-05T13:00:00Z",
        ],
        "container_ids": ["TIEDISP0002", "TIEHOLD0001"],
        "carriers": ["Union"],
        "status_counts": counts(ready=1, blocked=1),
    }
    assert by_carrier(report)["Union"] == {
        "carrier": "Union",
        "booking_ids": ["BK-TIE"],
        "container_ids": ["TIEDISP0002", "TIEHOLD0001"],
        "requires_temp_check": 0,
        "status_counts": counts(ready=1, blocked=1),
    }
    assert report["exceptions"] == [
        {
            "container_id": "TIEHOLD0001",
            "booking": "BK-TIE",
            "carrier": "Union",
            "status": "blocked",
            "primary_reason": "ACTIVE_HOLD",
            "last_event_utc": "2026-03-05T12:10:00Z",
            "minutes_from_window_start": 5,
        }
    ]


def test_boundary_and_grouping_edges(tmp_path: Path) -> None:
    """Boundary timestamps and grouped summaries should match the written rules."""
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "\n".join(
            [
                "container_id,booking,carrier,requires_temp_check",
                "MIX1000001,BK-MIX,Alpha,false",
                "MIX2000001,BK-MIX,Zeta,false",
                "MIXEDGE0001,BK-MIX,EdgeCarrier,false",
                "MIXHOLD0001,BK-MIX,Alpha,false",
                "SIXTEMP0001,BK-EDGE,EdgeCarrier,true",
                "SAMESTAMP0001,BK-EDGE,EdgeCarrier,false",
                "CUTOFF0001,BK-EDGE,EdgeCarrier,false",
                "",
            ]
        )
    )
    appointments = tmp_path / "appointments.csv"
    appointments.write_text(
        "\n".join(
            [
                "booking,window_start_local,window_end_local,timezone,capacity,carrier_cutoff_min",
                "BK-MIX,2026-04-10 10:00,2026-04-10 11:00,UTC,1,60",
                "BK-EDGE,2026-04-10 12:00,2026-04-10 14:00,UTC,3,30",
                "",
            ]
        )
    )
    events = tmp_path / "events.ndjson"
    events.write_text(
        "\n".join(
            [
                '{"container_id":"MIX1000001","type":"gate_in","timestamp":"2026-04-10T10:05:00Z"}',
                '{"container_id":"MIX2000001","type":"gate_in","timestamp":"2026-04-10T10:10:00Z"}',
                '{"container_id":"MIXEDGE0001","type":"gate_in","timestamp":"2026-04-10T10:15:00Z"}',
                '{"container_id":"MIXHOLD0001","type":"gate_in","timestamp":"2026-04-10T10:20:00Z"}',
                '{"container_id":"MIXHOLD0001","type":"hold","timestamp":"2026-04-10T10:30:00Z"}',
                '{"container_id":"SIXTEMP0001","type":"temp_check","timestamp":"2026-04-10T06:30:00Z"}',
                '{"container_id":"SIXTEMP0001","type":"gate_in","timestamp":"2026-04-10T12:30:00Z"}',
                '{"container_id":"SAMESTAMP0001","type":"gate_in","timestamp":"2026-04-10T12:20:00Z"}',
                '{"container_id":"SAMESTAMP0001","type":"inspect","timestamp":"2026-04-10T12:50:00Z"}',
                '{"container_id":"SAMESTAMP0001","type":"release","timestamp":"2026-04-10T12:50:00Z"}',
                '{"container_id":"CUTOFF0001","type":"gate_in","timestamp":"2026-04-10T12:31:00Z"}',
                "",
            ]
        )
    )

    report = run_yardcheck(manifest, appointments, events, tmp_path / "edges.json")
    assert report["generated_at"] == "2026-04-10T12:50:00Z"
    assert report["summary"] == counts(ready=2, blocked=1, stale=1, overbooked=3)

    entries = by_container(report)
    assert entries["SIXTEMP0001"]["status"] == "ready"
    assert entries["SIXTEMP0001"]["reason_codes"] == []
    assert entries["CUTOFF0001"]["status"] == "stale"
    assert entries["CUTOFF0001"]["reason_codes"] == ["CARRIER_CUTOFF_MISSED"]
    assert entries["SAMESTAMP0001"]["status"] == "ready"
    assert entries["SAMESTAMP0001"]["last_event_type"] == "release"
    assert entries["SAMESTAMP0001"]["last_event_utc"] == "2026-04-10T12:50:00Z"
    assert entries["MIXHOLD0001"]["status"] == "blocked"
    assert entries["MIXHOLD0001"]["reason_codes"] == ["ACTIVE_HOLD"]

    bookings = by_booking(report)
    assert bookings["BK-MIX"] == {
        "booking": "BK-MIX",
        "capacity": 1,
        "appointment_window_utc": [
            "2026-04-10T10:00:00Z",
            "2026-04-10T11:00:00Z",
        ],
        "container_ids": [
            "MIX1000001",
            "MIX2000001",
            "MIXEDGE0001",
            "MIXHOLD0001",
        ],
        "carriers": ["Alpha", "EdgeCarrier", "Zeta"],
        "status_counts": counts(blocked=1, overbooked=3),
    }
    assert bookings["BK-EDGE"]["status_counts"] == counts(ready=2, stale=1)

    carriers = by_carrier(report)
    assert carriers["Alpha"] == {
        "carrier": "Alpha",
        "booking_ids": ["BK-MIX"],
        "container_ids": ["MIX1000001", "MIXHOLD0001"],
        "requires_temp_check": 0,
        "status_counts": counts(blocked=1, overbooked=1),
    }
    assert carriers["EdgeCarrier"] == {
        "carrier": "EdgeCarrier",
        "booking_ids": ["BK-EDGE", "BK-MIX"],
        "container_ids": [
            "CUTOFF0001",
            "MIXEDGE0001",
            "SAMESTAMP0001",
            "SIXTEMP0001",
        ],
        "requires_temp_check": 1,
        "status_counts": counts(ready=2, stale=1, overbooked=1),
    }
    assert carriers["Zeta"]["status_counts"] == counts(overbooked=1)

    assert [
        (entry["status"], entry["container_id"], entry["primary_reason"])
        for entry in report["exceptions"]
    ] == [
        ("blocked", "MIXHOLD0001", "ACTIVE_HOLD"),
        ("overbooked", "MIX1000001", "CAPACITY_EXCEEDED"),
        ("overbooked", "MIX2000001", "CAPACITY_EXCEEDED"),
        ("overbooked", "MIXEDGE0001", "CAPACITY_EXCEEDED"),
        ("stale", "CUTOFF0001", "CARRIER_CUTOFF_MISSED"),
    ]
