"""Tests for go-struct-layout-analyzer task."""
import json
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')


def load_report():
    """Load and return the layout report JSON."""
    p = OUT_DIR / "layout_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def get_struct(name):
    """Get struct info by name from the report."""
    for s in R["structs"]:
        if s["name"] == name:
            return s
    pytest.fail(f"Struct '{name}' not found in report")


def get_field(struct_name, field_name):
    """Get field info by struct and field name."""
    s = get_struct(struct_name)
    for f in s["fields"]:
        if f["name"] == field_name:
            return f
    pytest.fail(f"Field '{field_name}' not found in struct '{struct_name}'")


# ─── Top-level structure tests ────────────────────────────────────────────────


def test_output_file_exists():
    """Verify the layout report file was created."""
    assert (OUT_DIR / "layout_report.json").is_file()


def test_platform_field():
    """Verify the platform is reported as linux_amd64."""
    assert R["platform"] == "linux_amd64"


def test_pointer_size():
    """Verify pointer size is 8 for amd64."""
    assert R["pointer_size"] == 8


def test_structs_key_exists():
    """Verify the structs array exists."""
    assert "structs" in R
    assert isinstance(R["structs"], list)


def test_all_structs_present():
    """Verify all 8 struct types from the input are analyzed."""
    names = [s["name"] for s in R["structs"]]
    expected = [
        "PacketHeader", "EventMarker", "Measurement",
        "AlignmentTrap", "NetworkPacket", "Handler", "Edge", "Graph"
    ]
    for e in expected:
        assert e in names, f"Missing struct: {e}"


def test_struct_declaration_order():
    """Verify structs appear in source declaration order."""
    names = [s["name"] for s in R["structs"]]
    expected_order = [
        "PacketHeader", "EventMarker", "Measurement",
        "AlignmentTrap", "NetworkPacket", "Handler", "Edge", "Graph"
    ]
    positions = []
    for e in expected_order:
        assert e in names, f"Missing struct: {e}"
        positions.append(names.index(e))
    assert positions == sorted(positions), "Structs not in declaration order"


# ─── PacketHeader tests ──────────────────────────────────────────────────────


def test_packet_header_size():
    """Verify PacketHeader total size accounts for alignment padding."""
    s = get_struct("PacketHeader")
    assert s["size"] == 32


def test_packet_header_alignment():
    """Verify PacketHeader alignment is 8 (max of int64 fields)."""
    s = get_struct("PacketHeader")
    assert s["alignment"] == 8


def test_packet_header_active_offset():
    """Verify Active bool field is at offset 0."""
    f = get_field("PacketHeader", "Active")
    assert f["offset"] == 0
    assert f["size"] == 1
    assert f["alignment"] == 1


def test_packet_header_seqnum_offset():
    """Verify SeqNum int64 field is at offset 8 (7 bytes padding after Active)."""
    f = get_field("PacketHeader", "SeqNum")
    assert f["offset"] == 8
    assert f["size"] == 8
    assert f["alignment"] == 8


def test_packet_header_priority_offset():
    """Verify Priority uint16 field is at offset 16."""
    f = get_field("PacketHeader", "Priority")
    assert f["offset"] == 16
    assert f["size"] == 2
    assert f["alignment"] == 2


def test_packet_header_timestamp_offset():
    """Verify Timestamp int64 is at offset 24 (6 bytes padding after Priority)."""
    f = get_field("PacketHeader", "Timestamp")
    assert f["offset"] == 24
    assert f["size"] == 8
    assert f["alignment"] == 8


def test_packet_header_total_padding():
    """Verify PacketHeader has 13 bytes total padding."""
    s = get_struct("PacketHeader")
    assert s["total_padding"] == 13


def test_packet_header_not_optimal():
    """Verify PacketHeader is detected as suboptimal."""
    s = get_struct("PacketHeader")
    assert s["is_optimal"] is False


def test_packet_header_optimal_size():
    """Verify PacketHeader optimal size is 24 after reordering."""
    s = get_struct("PacketHeader")
    assert s["optimal_size"] == 24


# ─── EventMarker tests (zero-size trailing field) ────────────────────────────


def test_event_marker_alignment():
    """Verify EventMarker alignment is 8."""
    s = get_struct("EventMarker")
    assert s["alignment"] == 8


def test_event_marker_timestamp_offset():
    """Verify Timestamp is at offset 0."""
    f = get_field("EventMarker", "Timestamp")
    assert f["offset"] == 0


def test_event_marker_category_offset():
    """Verify Category uint32 is at offset 8."""
    f = get_field("EventMarker", "Category")
    assert f["offset"] == 8
    assert f["size"] == 4


def test_event_marker_flags_offset():
    """Verify Flags uint32 is at offset 12."""
    f = get_field("EventMarker", "Flags")
    assert f["offset"] == 12
    assert f["size"] == 4


def test_event_marker_blank_field():
    """Verify the blank struct{} field is at offset 16 with size 0."""
    f = get_field("EventMarker", "_")
    assert f["offset"] == 16
    assert f["size"] == 0
    assert f["alignment"] == 1


# ─── Measurement tests (complex64 alignment) ─────────────────────────────────


def test_measurement_size():
    """Verify Measurement total size is 24."""
    s = get_struct("Measurement")
    assert s["size"] == 24


def test_measurement_sample_offset():
    """Verify complex64 Sample field is at offset 4 (alignment 4, not 8)."""
    f = get_field("Measurement", "Sample")
    assert f["offset"] == 4, (
        "complex64 has alignment 4, so Sample should be at offset 4 not 8"
    )


def test_measurement_sample_alignment():
    """Verify complex64 has alignment 4 (two float32s), not 8."""
    f = get_field("Measurement", "Sample")
    assert f["alignment"] == 4


def test_measurement_sample_size():
    """Verify complex64 has size 8."""
    f = get_field("Measurement", "Sample")
    assert f["size"] == 8


def test_measurement_scale_offset():
    """Verify Scale float64 is at offset 16 (needs alignment 8 after offset 12)."""
    f = get_field("Measurement", "Scale")
    assert f["offset"] == 16
    assert f["alignment"] == 8


def test_measurement_id_padding():
    """Verify no padding between ID and Sample (complex64 align=4, ID ends at 4)."""
    f = get_field("Measurement", "ID")
    assert f["padding_after"] == 0


def test_measurement_sample_padding():
    """Verify 4 bytes padding between Sample (ends at 12) and Scale (at 16)."""
    f = get_field("Measurement", "Sample")
    assert f["padding_after"] == 4


# ─── AlignmentTrap tests ([0]int64 alignment) ────────────────────────────────


def test_alignment_trap_size():
    """Verify AlignmentTrap size is 16 despite only 2 bytes of real data."""
    s = get_struct("AlignmentTrap")
    assert s["size"] == 16


def test_alignment_trap_alignment():
    """Verify [0]int64 forces struct alignment to 8."""
    s = get_struct("AlignmentTrap")
    assert s["alignment"] == 8


def test_alignment_trap_a_offset():
    """Verify field A is at offset 0."""
    f = get_field("AlignmentTrap", "A")
    assert f["offset"] == 0
    assert f["size"] == 1


def test_alignment_trap_blank_offset():
    """Verify [0]int64 blank field is at offset 8 (aligned to 8)."""
    f = get_field("AlignmentTrap", "_")
    assert f["offset"] == 8
    assert f["size"] == 0
    assert f["alignment"] == 8


def test_alignment_trap_b_offset():
    """Verify B is at offset 8 (shares offset with zero-size [0]int64)."""
    f = get_field("AlignmentTrap", "B")
    assert f["offset"] == 8
    assert f["size"] == 1


def test_alignment_trap_total_padding():
    """Verify AlignmentTrap has 14 bytes padding for just 2 bytes of data."""
    s = get_struct("AlignmentTrap")
    assert s["total_padding"] == 14


def test_alignment_trap_not_optimal():
    """Verify AlignmentTrap is suboptimal (reordering [0]int64 to front avoids penalty)."""
    s = get_struct("AlignmentTrap")
    assert s["is_optimal"] is False


def test_alignment_trap_optimal_size():
    """Verify AlignmentTrap optimal size is 8 (moving [0]int64 first eliminates waste)."""
    s = get_struct("AlignmentTrap")
    assert s["optimal_size"] == 8


# ─── NetworkPacket tests (heavily suboptimal) ─────────────────────────────────


def test_network_packet_size():
    """Verify NetworkPacket current size is 40 (heavily padded)."""
    s = get_struct("NetworkPacket")
    assert s["size"] == 40


def test_network_packet_alignment():
    """Verify NetworkPacket alignment is 8."""
    s = get_struct("NetworkPacket")
    assert s["alignment"] == 8


def test_network_packet_version_offset():
    """Verify Version uint8 at offset 0."""
    f = get_field("NetworkPacket", "Version")
    assert f["offset"] == 0


def test_network_packet_src_offset():
    """Verify Src uint64 at offset 8 (7 bytes padding after Version)."""
    f = get_field("NetworkPacket", "Src")
    assert f["offset"] == 8
    assert f["size"] == 8


def test_network_packet_ttl_offset():
    """Verify TTL uint8 at offset 16."""
    f = get_field("NetworkPacket", "TTL")
    assert f["offset"] == 16
    assert f["size"] == 1


def test_network_packet_dst_offset():
    """Verify Dst uint64 at offset 24 (7 bytes padding after TTL)."""
    f = get_field("NetworkPacket", "Dst")
    assert f["offset"] == 24
    assert f["size"] == 8


def test_network_packet_checksum_offset():
    """Verify Checksum uint32 at offset 32."""
    f = get_field("NetworkPacket", "Checksum")
    assert f["offset"] == 32
    assert f["size"] == 4


def test_network_packet_length_offset():
    """Verify Length uint16 at offset 36."""
    f = get_field("NetworkPacket", "Length")
    assert f["offset"] == 36
    assert f["size"] == 2


def test_network_packet_not_optimal():
    """Verify NetworkPacket is detected as suboptimal."""
    s = get_struct("NetworkPacket")
    assert s["is_optimal"] is False


def test_network_packet_optimal_size():
    """Verify NetworkPacket optimal size is 24 (huge savings of 16 bytes)."""
    s = get_struct("NetworkPacket")
    assert s["optimal_size"] == 24


def test_network_packet_total_padding():
    """Verify NetworkPacket has 16 bytes total padding."""
    s = get_struct("NetworkPacket")
    assert s["total_padding"] == 16


# ─── Handler tests (interface, func, string sizes) ───────────────────────────


def test_handler_size():
    """Verify Handler total size is 48."""
    s = get_struct("Handler")
    assert s["size"] == 48


def test_handler_name_field():
    """Verify string field Name has size 16, alignment 8."""
    f = get_field("Handler", "Name")
    assert f["size"] == 16
    assert f["alignment"] == 8
    assert f["offset"] == 0


def test_handler_callback_field():
    """Verify function field Callback has size 8, alignment 8."""
    f = get_field("Handler", "Callback")
    assert f["size"] == 8
    assert f["alignment"] == 8
    assert f["offset"] == 16


def test_handler_processor_field():
    """Verify interface{} field Processor has size 16, alignment 8."""
    f = get_field("Handler", "Processor")
    assert f["size"] == 16
    assert f["alignment"] == 8
    assert f["offset"] == 24


def test_handler_priority_field():
    """Verify int32 Priority at offset 40."""
    f = get_field("Handler", "Priority")
    assert f["size"] == 4
    assert f["offset"] == 40


def test_handler_enabled_field():
    """Verify bool Enabled at offset 44."""
    f = get_field("Handler", "Enabled")
    assert f["size"] == 1
    assert f["offset"] == 44


def test_handler_total_padding():
    """Verify Handler has 3 bytes tail padding."""
    s = get_struct("Handler")
    assert s["total_padding"] == 3


# ─── Edge tests (named types resolution) ─────────────────────────────────────


def test_edge_size():
    """Verify Edge size is 16 (two uint32s + one float64, no internal padding)."""
    s = get_struct("Edge")
    assert s["size"] == 16


def test_edge_alignment():
    """Verify Edge alignment is 8 (from Score=float64)."""
    s = get_struct("Edge")
    assert s["alignment"] == 8


def test_edge_from_field():
    """Verify NodeID (=uint32) From field has size 4, alignment 4."""
    f = get_field("Edge", "From")
    assert f["size"] == 4
    assert f["alignment"] == 4
    assert f["offset"] == 0


def test_edge_to_field():
    """Verify NodeID (=uint32) To field at offset 4."""
    f = get_field("Edge", "To")
    assert f["size"] == 4
    assert f["alignment"] == 4
    assert f["offset"] == 4


def test_edge_weight_field():
    """Verify Score (=float64) Weight field at offset 8."""
    f = get_field("Edge", "Weight")
    assert f["size"] == 8
    assert f["alignment"] == 8
    assert f["offset"] == 8


def test_edge_no_padding():
    """Verify Edge has zero padding (perfectly packed)."""
    s = get_struct("Edge")
    assert s["total_padding"] == 0


def test_edge_is_optimal():
    """Verify Edge is already in optimal layout."""
    s = get_struct("Edge")
    assert s["is_optimal"] is True


# ─── Graph tests (slice, map, bool) ──────────────────────────────────────────


def test_graph_size():
    """Verify Graph total size is 48."""
    s = get_struct("Graph")
    assert s["size"] == 48


def test_graph_id_field():
    """Verify int64 ID at offset 0."""
    f = get_field("Graph", "ID")
    assert f["offset"] == 0
    assert f["size"] == 8


def test_graph_edges_field():
    """Verify slice field Edges has size 24 (ptr+len+cap) at offset 8."""
    f = get_field("Graph", "Edges")
    assert f["offset"] == 8
    assert f["size"] == 24
    assert f["alignment"] == 8


def test_graph_metadata_field():
    """Verify map field Metadata has size 8 (pointer) at offset 32."""
    f = get_field("Graph", "Metadata")
    assert f["offset"] == 32
    assert f["size"] == 8
    assert f["alignment"] == 8


def test_graph_directed_field():
    """Verify bool Directed at offset 40."""
    f = get_field("Graph", "Directed")
    assert f["offset"] == 40
    assert f["size"] == 1


def test_graph_total_padding():
    """Verify Graph has 7 bytes tail padding."""
    s = get_struct("Graph")
    assert s["total_padding"] == 7


# ─── Optimal order tests ─────────────────────────────────────────────────────


def test_packet_header_optimal_order():
    """Verify PacketHeader optimal order: align desc, size desc, decl order tiebreaker."""
    s = get_struct("PacketHeader")
    assert s["optimal_order"] == ["SeqNum", "Timestamp", "Priority", "Active"]


def test_network_packet_optimal_order():
    """Verify NetworkPacket optimal order: align desc, size desc, decl order tiebreaker."""
    s = get_struct("NetworkPacket")
    assert s["optimal_order"] == [
        "Src", "Dst", "Checksum", "Length", "Version", "TTL"
    ]


def test_handler_optimal_order():
    """Verify Handler optimal order: align desc, size desc, decl order tiebreaker."""
    s = get_struct("Handler")
    assert s["optimal_order"] == [
        "Name", "Processor", "Callback", "Priority", "Enabled"
    ]


def test_graph_optimal_order():
    """Verify Graph optimal order: align desc, size desc, decl order tiebreaker."""
    s = get_struct("Graph")
    assert s["optimal_order"] == [
        "Edges", "ID", "Metadata", "Directed"
    ]


# ─── Field type string tests ─────────────────────────────────────────────────


def test_named_type_reported_as_source():
    """Verify named types are reported with source-level name (NodeID not uint32)."""
    f = get_field("Edge", "From")
    assert f["type"] == "NodeID"


def test_score_type_reported():
    """Verify Score named type appears in Edge.Weight type field."""
    f = get_field("Edge", "Weight")
    assert f["type"] == "Score"


def test_interface_type_string():
    """Verify interface{} fields report type as interface{} or any."""
    f = get_field("Handler", "Processor")
    assert f["type"] in ("interface{}", "any")


# ─── Cross-field consistency tests ────────────────────────────────────────────


def test_padding_sums_match():
    """Verify total_padding equals sum of all padding_after values for each struct."""
    for s in R["structs"]:
        field_padding_sum = sum(f["padding_after"] for f in s["fields"])
        assert s["total_padding"] == field_padding_sum, (
            f"{s['name']}: total_padding={s['total_padding']} != "
            f"sum(padding_after)={field_padding_sum}"
        )


def test_size_equals_data_plus_padding():
    """Verify struct size equals sum of field sizes plus total padding."""
    for s in R["structs"]:
        data_size = sum(f["size"] for f in s["fields"])
        assert s["size"] == data_size + s["total_padding"], (
            f"{s['name']}: size={s['size']} != data({data_size}) + "
            f"padding({s['total_padding']})"
        )


def test_optimal_size_not_greater_than_current():
    """Verify optimal_size is always <= current size."""
    for s in R["structs"]:
        assert s["optimal_size"] <= s["size"], (
            f"{s['name']}: optimal_size={s['optimal_size']} > size={s['size']}"
        )


def test_is_optimal_consistent_with_sizes():
    """Verify is_optimal is True iff optimal_size == size."""
    for s in R["structs"]:
        if s["is_optimal"]:
            assert s["optimal_size"] == s["size"], (
                f"{s['name']}: marked optimal but optimal_size != size"
            )
        else:
            assert s["optimal_size"] < s["size"], (
                f"{s['name']}: marked not optimal but optimal_size >= size"
            )


def test_field_offsets_non_decreasing():
    """Verify field offsets are non-decreasing within each struct."""
    for s in R["structs"]:
        offsets = [f["offset"] for f in s["fields"]]
        for i in range(1, len(offsets)):
            assert offsets[i] >= offsets[i-1], (
                f"{s['name']}: field offsets not non-decreasing at index {i}"
            )


def test_field_count_correct():
    """Verify each struct has the expected number of fields."""
    expected_counts = {
        "PacketHeader": 4,
        "EventMarker": 4,
        "Measurement": 3,
        "AlignmentTrap": 3,
        "NetworkPacket": 6,
        "Handler": 5,
        "Edge": 3,
        "Graph": 4,
    }
    for s in R["structs"]:
        if s["name"] in expected_counts:
            assert len(s["fields"]) == expected_counts[s["name"]], (
                f"{s['name']}: expected {expected_counts[s['name']]} fields, "
                f"got {len(s['fields'])}"
            )
