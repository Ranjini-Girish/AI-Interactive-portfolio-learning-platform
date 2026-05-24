"""Verifier tests for the memory layout audit tool."""

from __future__ import annotations

import json
import math
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
REPORT_PATH = OUT_DIR / "layout_report.json"


def load_report() -> dict:
    """Load and return parsed JSON from the output directory."""
    assert REPORT_PATH.is_file(), f"Missing output file: {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


R = load_report()

_EXPECTED_IDS = sorted(
    [
        "type_01_simple",
        "type_02_reorder",
        "type_03_packed",
        "type_04_align16",
        "type_05_nested",
        "type_06_array",
        "type_07_enum_basic",
        "type_08_enum_niche",
        "type_09_complex",
        "type_10_zst",
        "type_11_multi_array",
        "type_12_deep_nest",
    ]
)


def align_up(off: int, a: int) -> int:
    """Round offset up to next multiple of alignment."""
    if a <= 1:
        return off
    m = off % a
    if m == 0:
        return off
    return off + (a - m)


def _find(tid: str) -> dict:
    for t in R["types"]:
        if t["id"] == tid:
            return t
    pytest.fail(f"missing type {tid}")


# ═══════════════════════════════════════════════════════════════════════════════


def test_output_file_exists() -> None:
    """Verify the main output file was created."""
    assert REPORT_PATH.is_file()


def test_top_level_keys_exact() -> None:
    """Verify the output contains exactly the three required top-level keys."""
    assert set(R.keys()) == {"platform", "types", "summary"}


def test_platform_x86_string() -> None:
    """Verify the platform field is the string x86_64."""
    assert R["platform"] == "x86_64"


def test_types_is_list_twelve() -> None:
    """Verify the types array has exactly twelve entries."""
    assert isinstance(R["types"], list)
    assert len(R["types"]) == 12


@pytest.mark.parametrize("tid", _EXPECTED_IDS)
def test_every_expected_id_present(tid: str) -> None:
    """Verify each expected type id appears in the report."""
    assert tid in {_t["id"] for _t in R["types"]}


@pytest.mark.parametrize("tid", ["type_zzz", "bogus"])
def test_unknown_ids_absent(tid: str) -> None:
    """Verify fabricated ids are not present in the report."""
    assert tid not in {_t["id"] for _t in R["types"]}


def test_types_sorted_lexicographically() -> None:
    """Verify the types array is sorted ascending by id."""
    ids = [t["id"] for t in R["types"]]
    assert ids == sorted(ids)
    assert ids == _EXPECTED_IDS


@pytest.mark.parametrize(
    ("left", "right"),
    [(f, _EXPECTED_IDS[k + 1]) for k, f in enumerate(_EXPECTED_IDS[:-1])],
)
def test_adjacent_lexicographic_order_strict(left: str, right: str) -> None:
    """Verify each pair of adjacent type ids is in strict ascending order."""
    assert left < right


def test_summary_keys_exact() -> None:
    """Verify the summary object contains all nine required keys."""
    req = {
        "total_types",
        "total_size_all_types",
        "total_padding_all_types",
        "padding_ratio",
        "zst_count",
        "niche_optimized_count",
        "max_alignment",
        "largest_type",
        "most_padded_type",
    }
    assert set(R["summary"]) == req


def test_summary_total_types_twelve() -> None:
    """Verify total_types equals 12."""
    assert R["summary"]["total_types"] == 12


def test_summary_aggregate_sizes_two_six_one() -> None:
    """Verify the sum of all type sizes is 261."""
    assert R["summary"]["total_size_all_types"] == 261


def test_summary_aggregate_padding_sixty_six() -> None:
    """Verify the sum of all total_padding values is 66."""
    assert R["summary"]["total_padding_all_types"] == 66


def test_summary_padding_ratio_float_rounded_six_decimal() -> None:
    """Verify padding_ratio is a float matching round(66/261, 6)."""
    assert isinstance(R["summary"]["padding_ratio"], float)
    expected = round(66 / 261, 6)
    assert math.isclose(
        R["summary"]["padding_ratio"], expected, rel_tol=0.0, abs_tol=1e-9
    )


def test_summary_zst_count_one() -> None:
    """Verify exactly one zero-sized type is reported."""
    assert R["summary"]["zst_count"] == 1


def test_summary_niche_count_one() -> None:
    """Verify exactly one niche-optimized enum is reported."""
    assert R["summary"]["niche_optimized_count"] == 1


def test_summary_max_alignment_sixteen() -> None:
    """Verify the maximum alignment across all types is 16."""
    assert R["summary"]["max_alignment"] == 16


def test_summary_largest_is_multi_array() -> None:
    """Verify the largest type by size is type_11_multi_array (48 bytes)."""
    assert R["summary"]["largest_type"] == "type_11_multi_array"


def test_summary_most_padded_is_complex() -> None:
    """Verify the most-padded type is type_09_complex (16 bytes padding)."""
    assert R["summary"]["most_padded_type"] == "type_09_complex"


def test_manual_sum_sizes_matches_summary() -> None:
    """Verify the manual sum of individual type sizes equals the summary value."""
    manual = sum(t["size"] for t in R["types"])
    assert manual == R["summary"]["total_size_all_types"]


def test_manual_sum_padding_matches_summary() -> None:
    """Verify the manual sum of individual padding totals equals the summary value."""
    manual = sum(t["total_padding"] for t in R["types"])
    assert manual == R["summary"]["total_padding_all_types"]


@pytest.mark.parametrize("tid", _EXPECTED_IDS)
def test_each_type_positive_alignment_pow2_when_not_one(tid: str) -> None:
    """Verify every type's alignment is a positive power of two (or 1)."""
    t = _find(tid)
    al = t["alignment"]
    assert al >= 1
    assert al == 1 or (al & (al - 1) == 0)


def test_type_01_size_align() -> None:
    """Verify type_01_simple has size=12, alignment=4, repr=C, not a ZST."""
    t = _find("type_01_simple")
    assert t["size"] == 12
    assert t["alignment"] == 4
    assert t["repr"] == "C"
    assert not t["is_zst"]


@pytest.mark.parametrize(
    ("name", "offset", "pb"),
    [
        ("a", 0, 0),
        ("b", 4, 3),
        ("c", 8, 0),
    ],
)
def test_type_01_field_offsets_padding(name: str, offset: int, pb: int) -> None:
    """Verify each field in type_01_simple has the correct offset and padding_before."""
    t = _find("type_01_simple")
    fld = next(f for f in t["fields"] if f["name"] == name)
    assert fld["offset"] == offset
    assert fld["padding_before"] == pb


def test_type_01_trailing_and_total_padding() -> None:
    """Verify type_01_simple has trailing_padding=2 and total_padding=5."""
    t = _find("type_01_simple")
    assert t["trailing_padding"] == 2
    assert t["total_padding"] == 5


def test_type_02_field_order_reordered_y_z_w_x() -> None:
    """Verify repr(Rust) reorders type_02 fields by descending align then size."""
    t = _find("type_02_reorder")
    assert t["field_order"] == ["y", "z", "w", "x"]
    assert t["repr"] == "Rust"
    assert t["alignment"] == 8
    assert t["total_padding"] == 1


def test_type_02_field_y_at_zero_and_x_fourteen() -> None:
    """Verify field y is at offset 0 and field x at offset 14 after reordering."""
    t = _find("type_02_reorder")
    by = next(f for f in t["fields"] if f["name"] == "y")
    bx = next(f for f in t["fields"] if f["name"] == "x")
    assert by["offset"] == 0
    assert bx["offset"] == 14


@pytest.mark.parametrize("fn", ["a", "b", "c"])
def test_type_03_packed_zero_padding_before(fn: str) -> None:
    """Verify every field in packed struct has zero padding_before."""
    t = _find("type_03_packed")
    f = next(x for x in t["fields"] if x["name"] == fn)
    assert f["padding_before"] == 0


def test_type_03_packed_offsets_sizes_total() -> None:
    """Verify packed struct has contiguous field offsets and total size=13, align=1."""
    t = _find("type_03_packed")
    m = {f["name"]: f for f in t["fields"]}
    assert m["a"]["offset"] == 0 and m["a"]["size"] == 1
    assert m["b"]["offset"] == 1 and m["b"]["size"] == 8
    assert m["c"]["offset"] == 9 and m["c"]["size"] == 4
    assert t["size"] == 13
    assert t["alignment"] == 1
    assert t["total_padding"] == 0


def test_type_04_align_sixteen_size_sixteen() -> None:
    """Verify align(16) override yields size=16, alignment=16, total_padding=11."""
    t = _find("type_04_align16")
    assert t["repr"].startswith("align(")
    assert t["alignment"] == 16
    assert t["size"] == 16
    assert t["total_padding"] == 11


def test_type_05_nested_inner_twelve_tail_sixteen() -> None:
    """Verify nested struct inner field has size=12 at offset 4, tail at offset 16."""
    t = _find("type_05_nested")
    inn = next(f for f in t["fields"] if f["name"] == "inner")
    assert inn["size"] == 12
    assert inn["alignment"] == 4
    assert inn["offset"] == 4
    tail = next(f for f in t["fields"] if f["name"] == "tail")
    assert tail["offset"] == 16
    assert tail["padding_before"] == 0


@pytest.mark.parametrize(
    ("name", "payload_size", "payload_alignment"),
    [
        ("Empty", 0, 1),
        ("Single", 4, 4),
        ("Double", 16, 8),
    ],
)
def test_type_07_enum_variant_payload_metrics(
    name: str, payload_size: int, payload_alignment: int
) -> None:
    """Verify each enum variant has the expected payload size and alignment."""
    t = _find("type_07_enum_basic")
    v = next(x for x in t["variants"] if x["name"] == name)
    assert v["payload_size"] == payload_size
    assert v["payload_alignment"] == payload_alignment


def test_type_07_enum_structure() -> None:
    """Verify repr(C) enum has disc={size:1,align:1}, total_padding=7, size=24."""
    t = _find("type_07_enum_basic")
    assert t["discriminant"] == {"size": 1, "alignment": 1}
    assert t["total_padding"] == 7
    assert t["size"] == 24
    assert t["field_order"] is None


def test_type_08_niche_structure() -> None:
    """Verify pointer-niche enum has null discriminant, niche_optimized=true, size=8."""
    t = _find("type_08_enum_niche")
    assert t["discriminant"] is None
    assert t["niche_optimized"] is True
    assert t["repr"] == "Rust"
    assert t["size"] == 8
    assert t["total_padding"] == 0


def test_type_08_some_variant_eight_align_eight() -> None:
    """Verify the Some variant of niche enum reports payload_size=8, payload_alignment=8."""
    t = _find("type_08_enum_niche")
    v = next(x for x in t["variants"] if x["name"] == "Some")
    assert v["payload_size"] == 8
    assert v["payload_alignment"] == 8


def test_type_09_weight_offset_twenty_four() -> None:
    """Verify field weight in type_09 is at offset 24 with 4 bytes of padding before."""
    t = _find("type_09_complex")
    w = next(f for f in t["fields"] if f["name"] == "weight")
    assert w["offset"] == 24
    assert w["padding_before"] == 4


def test_type_09_most_padded_sixteen() -> None:
    """Verify type_09_complex has total_padding=16."""
    assert _find("type_09_complex")["total_padding"] == 16


def test_type_10_zst() -> None:
    """Verify the empty struct is a ZST with size=0, align=1, empty fields and order."""
    t = _find("type_10_zst")
    assert t["is_zst"] is True
    assert t["size"] == 0
    assert t["fields"] == []
    assert t["field_order"] == []
    assert t["total_padding"] == 0


def test_type_11_arrays_and_order() -> None:
    """Verify repr(Rust) with array fields reorders to [matrix,index,pairs,small]."""
    t = _find("type_11_multi_array")
    fo = ["matrix", "index", "pairs", "small"]
    assert t["field_order"] == fo
    mx = next(f for f in t["fields"] if f["name"] == "matrix")
    assert mx["size"] == 32
    pr = next(f for f in t["fields"] if f["name"] == "pairs")
    assert pr["size"] == 6
    assert t["alignment"] == 8
    assert t["size"] == 48


def test_both_struct_and_enum_kinds_present() -> None:
    """Verify the report contains at least one struct and one enum type."""
    ks = {_t["kind"] for _t in R["types"]}
    assert "struct" in ks
    assert "enum" in ks


@pytest.mark.parametrize("tid", ["type_06_array"])
def test_type_06_data_array_field(tid: str) -> None:
    """Verify type_06 tag starts at 0, data has padding_before=3, data size=12."""
    t = _find(tid)
    tg = next(f for f in t["fields"] if f["name"] == "tag")
    data = next(f for f in t["fields"] if f["name"] == "data")
    assert tg["offset"] == 0
    assert data["padding_before"] == 3
    assert data["size"] == 12


def test_enums_have_null_field_order() -> None:
    """Verify all enum entries have field_order set to null."""
    for t in R["types"]:
        if t["kind"] == "enum":
            assert t["field_order"] is None


def test_structs_have_field_order_arrays() -> None:
    """Verify all struct entries have field_order as a list."""
    for t in R["types"]:
        if t["kind"] != "struct":
            continue
        fo = t["field_order"]
        assert isinstance(fo, list)


def test_struct_kind_never_contains_enum_keys_in_report() -> None:
    """Verify struct entries never include variants or discriminant keys."""
    for t in R["types"]:
        if t["kind"] == "struct":
            assert "variants" not in t
            assert "discriminant" not in t


def test_enum_kind_has_variants_always() -> None:
    """Verify enum entries always include variants list and never include fields."""
    for t in R["types"]:
        if t["kind"] == "enum":
            assert isinstance(t["variants"], list)
            assert "fields" not in t


@pytest.mark.parametrize("tid", ["type_07_enum_basic", "type_08_enum_niche"])
def test_enum_reports_discriminant_key_shape(tid: str) -> None:
    """Verify discriminant is dict for non-niche enums and null for niche enums."""
    t = _find(tid)
    if t["niche_optimized"]:
        assert "discriminant" in t
        assert t["discriminant"] is None
    else:
        assert isinstance(t["discriminant"], dict)


@pytest.mark.parametrize("tid", sorted([t["id"] for t in R["types"]]))
def test_niche_exclusive_to_known_id_when_true(tid: str) -> None:
    """Verify only type_08_enum_niche has niche_optimized=true."""
    if _find(tid)["niche_optimized"]:
        assert tid == "type_08_enum_niche"


def test_max_alignment_sixteen_on_align16_type_only_tie() -> None:
    """Verify type_04_align16 is among the types with alignment 16."""
    highs = {
        _t["id"]: _t["alignment"] for _t in R["types"] if _t["alignment"] == 16
    }
    assert "type_04_align16" in highs


def test_packed_declaration_field_order_stable() -> None:
    """Verify packed struct preserves declaration order in field_order."""
    fo = _find("type_03_packed")["field_order"]
    assert fo == ["a", "b", "c"]


@pytest.mark.parametrize("tid", ["type_03_packed", "type_08_enum_niche"])
def test_zero_explicit_total_padding(tid: str) -> None:
    """Verify packed struct and niche enum both have zero total_padding."""
    assert _find(tid)["total_padding"] == 0


def test_type_06_count_offset_sixteen() -> None:
    """Verify the count field in type_06_array is at offset 16."""
    c = next(f for f in _find("type_06_array")["fields"] if f["name"] == "count")
    assert c["offset"] == 16


def test_type_06_trailing_two() -> None:
    """Verify type_06_array has trailing_padding=2."""
    assert _find("type_06_array")["trailing_padding"] == 2


def test_cross_struct_padding_consistency_type_09() -> None:
    """Verify sum of padding_before plus trailing equals total_padding for type_09."""
    t = _find("type_09_complex")
    pb = sum(f["padding_before"] for f in t["fields"])
    assert pb + t["trailing_padding"] == t["total_padding"]


def test_cross_struct_padding_consistency_type_12() -> None:
    """Verify padding consistency and total size=40 for type_12_deep_nest."""
    t = _find("type_12_deep_nest")
    pb = sum(f["padding_before"] for f in t["fields"])
    assert pb + t["trailing_padding"] == t["total_padding"]
    assert t["size"] == 40


def test_type_12_suffix_offset_thirty_two() -> None:
    """Verify the suffix field in type_12_deep_nest is at offset 32."""
    d = _find("type_12_deep_nest")
    assert next(f for f in d["fields"] if f["name"] == "suffix")["offset"] == 32


def test_no_duplicate_report_ids() -> None:
    """Verify there are no duplicate type ids in the report."""
    ids = [t["id"] for t in R["types"]]
    assert len(ids) == len(set(ids))


def test_known_repr_family_present() -> None:
    """Verify the report covers at least C, Rust, and packed representations."""
    reps = {_t["repr"] for _t in R["types"]}
    assert {"C", "Rust", "packed"}.issubset(reps)


@pytest.mark.parametrize(
    "tid", sorted([t["id"] for t in R["types"] if t["is_zst"]])
)
def test_exactly_single_zst_tid(tid: str) -> None:
    """Verify the only zero-sized type is type_10_zst."""
    assert tid == "type_10_zst"


def test_niche_is_non_c_repr() -> None:
    """Verify the niche-optimized enum does not use repr(C)."""
    t = _find("type_08_enum_niche")
    assert t["repr"] != "C"


def test_enum_size_math_matches_oracle_formula_type_07() -> None:
    """Verify type_07 enum size matches the computed formula from its parts."""
    t = _find("type_07_enum_basic")
    ds = t["discriminant"]["size"]
    da = t["discriminant"]["alignment"]
    max_ps = max(v["payload_size"] for v in t["variants"])
    max_pa = max(v["payload_alignment"] for v in t["variants"])
    u0 = align_up(ds, max_pa)
    assert t["total_padding"] == u0 - ds
    enum_align = max(da, max_pa)
    expect = align_up(u0 + max_ps, enum_align)
    assert t["size"] == expect


@pytest.mark.parametrize("tid", _EXPECTED_IDS)
def test_every_type_has_standard_core_keys(tid: str) -> None:
    """Verify each type entry has the seven standard keys."""
    t = _find(tid)
    assert {
        "id", "kind", "repr", "size", "alignment", "is_zst", "niche_optimized"
    }.issubset(set(t.keys()))


@pytest.mark.parametrize(
    "tid", sorted([x for x in _EXPECTED_IDS if "enum" not in x])
)
def test_sizes_snapshot_non_enum_subset(tid: str) -> None:
    """Verify each non-enum type has the exact expected size."""
    expected_sizes = {
        "type_01_simple": 12,
        "type_02_reorder": 16,
        "type_03_packed": 13,
        "type_04_align16": 16,
        "type_05_nested": 24,
        "type_06_array": 20,
        "type_09_complex": 40,
        "type_10_zst": 0,
        "type_11_multi_array": 48,
        "type_12_deep_nest": 40,
    }
    assert _find(tid)["size"] == expected_sizes[tid]


@pytest.mark.parametrize(
    "tid", sorted([x for x in _EXPECTED_IDS if "enum" in x])
)
def test_sizes_snapshot_enums(tid: str) -> None:
    """Verify each enum type has the exact expected size."""
    sizes = {"type_07_enum_basic": 24, "type_08_enum_niche": 8}
    assert _find(tid)["size"] == sizes[tid]


def test_most_padded_leads_margin_over_second_place() -> None:
    """Verify type_09_complex has strictly more padding than the runner-up."""
    paddings = sorted(
        ((t["id"], t["total_padding"]) for t in R["types"]),
        key=lambda kv: (-kv[1], kv[0]),
    )
    assert paddings[0][0] == "type_09_complex"
    assert paddings[0][1] > paddings[1][1]


def test_negative_no_extra_top_metadata_keys() -> None:
    """Verify no unexpected top-level key like metadata exists."""
    assert "metadata" not in R


def test_struct_required_field_shape_when_nonempty() -> None:
    """Verify every struct field record has exactly the five expected keys."""
    for t in R["types"]:
        if t["kind"] != "struct":
            continue
        for f in t["fields"]:
            assert set(f.keys()) == {
                "name", "offset", "size", "alignment", "padding_before"
            }


def test_variant_records_have_three_keys_each() -> None:
    """Verify every enum variant record has exactly name, payload_size, payload_alignment."""
    for t in R["types"]:
        if t["kind"] != "enum":
            continue
        for v in t["variants"]:
            assert set(v.keys()) == {"name", "payload_size", "payload_alignment"}


def test_type_05_size_twenty_four_align_eight() -> None:
    """Verify type_05_nested has size=24 and alignment=8."""
    t = _find("type_05_nested")
    assert t["size"] == 24
    assert t["alignment"] == 8


def test_type_05_total_padding_three() -> None:
    """Verify type_05_nested has total_padding=3 from the header-to-inner gap."""
    assert _find("type_05_nested")["total_padding"] == 3


def test_type_12_nested_field_size_twenty_four() -> None:
    """Verify the nested field inside type_12 inherits type_05's size of 24."""
    t = _find("type_12_deep_nest")
    nested = next(f for f in t["fields"] if f["name"] == "nested")
    assert nested["size"] == 24
    assert nested["alignment"] == 8


def test_type_12_total_padding_thirteen() -> None:
    """Verify type_12_deep_nest has total_padding=13."""
    assert _find("type_12_deep_nest")["total_padding"] == 13


def test_type_12_prefix_at_zero() -> None:
    """Verify the prefix field in type_12 is at offset 0."""
    t = _find("type_12_deep_nest")
    prefix = next(f for f in t["fields"] if f["name"] == "prefix")
    assert prefix["offset"] == 0
    assert prefix["size"] == 2


def test_type_12_nested_offset_eight() -> None:
    """Verify the nested field in type_12 is at offset 8 due to alignment padding."""
    t = _find("type_12_deep_nest")
    nested = next(f for f in t["fields"] if f["name"] == "nested")
    assert nested["offset"] == 8
    assert nested["padding_before"] == 6


def test_type_09_field_count_six() -> None:
    """Verify type_09_complex has exactly 6 fields."""
    assert len(_find("type_09_complex")["fields"]) == 6


def test_type_09_flags_at_zero_id_at_eight() -> None:
    """Verify type_09 flags at offset 0 and id at offset 8 with 7 padding."""
    t = _find("type_09_complex")
    flags = next(f for f in t["fields"] if f["name"] == "flags")
    fid = next(f for f in t["fields"] if f["name"] == "id")
    assert flags["offset"] == 0
    assert fid["offset"] == 8
    assert fid["padding_before"] == 7


def test_type_09_trailing_padding_five() -> None:
    """Verify type_09_complex has trailing_padding=5."""
    assert _find("type_09_complex")["trailing_padding"] == 5


def test_type_02_size_sixteen() -> None:
    """Verify type_02_reorder has size=16 after field reordering."""
    assert _find("type_02_reorder")["size"] == 16


def test_type_11_trailing_padding_five() -> None:
    """Verify type_11_multi_array has trailing_padding=5."""
    assert _find("type_11_multi_array")["trailing_padding"] == 5


def test_type_01_field_order_declaration() -> None:
    """Verify repr(C) struct preserves declaration order [a, b, c]."""
    assert _find("type_01_simple")["field_order"] == ["a", "b", "c"]


def test_align16_repr_string_exact() -> None:
    """Verify the repr string is exactly 'align(16)' for type_04."""
    assert _find("type_04_align16")["repr"] == "align(16)"


def test_type_10_alignment_one() -> None:
    """Verify the empty ZST struct has alignment 1."""
    assert _find("type_10_zst")["alignment"] == 1


def test_type_03_field_b_alignment_stored_correctly() -> None:
    """Verify packed struct still reports the natural alignment of each field."""
    t = _find("type_03_packed")
    b = next(f for f in t["fields"] if f["name"] == "b")
    assert b["alignment"] == 8


def test_type_07_enum_alignment_eight() -> None:
    """Verify enum_basic overall alignment is 8."""
    assert _find("type_07_enum_basic")["alignment"] == 8


def test_type_07_trailing_padding_zero() -> None:
    """Verify enum_basic has no trailing padding since 24 % 8 == 0."""
    assert _find("type_07_enum_basic")["trailing_padding"] == 0
