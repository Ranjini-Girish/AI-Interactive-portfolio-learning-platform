"""Tests for the 2D Computational Geometry Auditor."""

import json
import hashlib
import math
import os
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_ROOT", "/app"))
REPORT_PATH = APP / "output" / "geometry_audit.json"
CONFIG_DIR = APP / "config"
SCENES_DIR = APP / "scenes"
QUERIES_DIR = APP / "queries"


@pytest.fixture(scope="session")
def report():
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    with open(REPORT_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def policy():
    with open(CONFIG_DIR / "policy.json") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def scenes():
    s = {}
    for fn in sorted(os.listdir(SCENES_DIR)):
        if fn.endswith(".json"):
            with open(SCENES_DIR / fn) as f:
                d = json.load(f)
                s[d["scene_id"]] = d
    return s


@pytest.fixture(scope="session")
def queries():
    q = {}
    for fn in sorted(os.listdir(QUERIES_DIR)):
        if fn.endswith(".json"):
            with open(QUERIES_DIR / fn) as f:
                d = json.load(f)
                q[d["scene_id"]] = d
    return q


def compute_source_hashes():
    hashes = {}
    for d in [CONFIG_DIR, SCENES_DIR, QUERIES_DIR]:
        for dp, dns, fns in os.walk(d):
            dns.sort()
            for fn in sorted(fns):
                fp = os.path.join(dp, fn)
                rel = os.path.relpath(fp, APP).replace("\\", "/")
                with open(fp, "rb") as fh:
                    hashes[rel] = hashlib.sha256(fh.read()).hexdigest()
    return dict(sorted(hashes.items()))


def get_scene_audit(report, scene_id):
    return next(a for a in report["scene_audits"] if a["scene_id"] == scene_id)


FIXTURE_HASHES = {
    "config/policy.json": "4595279f7003cae27f0fe0934666efd777520502ca00616cac3e7c4796074bb0",
}


# === STRUCTURAL TESTS ===

def test_01_report_exists():
    """geometry_audit.json must exist at /app/output/."""
    assert REPORT_PATH.exists()


def test_02_report_valid_json(report):
    """Report must be a valid JSON object (dict)."""
    assert isinstance(report, dict)


def test_03_top_level_keys(report):
    """Report must contain exactly: schema_version, summary, source_sha256, scene_audits, findings."""
    expected = {"schema_version", "summary", "source_sha256", "scene_audits", "findings"}
    assert set(report.keys()) == expected


def test_04_schema_version(report):
    """schema_version must be 1."""
    assert report["schema_version"] == 1


def test_05_summary_keys(report):
    """Summary must include total_scenes, total_polygons, total_findings, findings_by_type, findings_by_severity."""
    s = report["summary"]
    expected = {"total_scenes", "total_polygons", "total_findings",
                "findings_by_type", "findings_by_severity"}
    assert set(s.keys()) == expected


def test_06_summary_counts(report, scenes):
    """Summary counts must match actual scene count, polygon count, and findings count."""
    s = report["summary"]
    assert s["total_scenes"] == len(scenes)
    total_poly = sum(len(sc.get("polygons", [])) for sc in scenes.values())
    assert s["total_polygons"] == total_poly
    assert s["total_findings"] == len(report["findings"])


def test_07_source_hashes_present(report):
    """source_sha256 must be a dict with at least 25 file hashes (config + scenes + queries)."""
    hashes = report["source_sha256"]
    assert isinstance(hashes, dict)
    assert len(hashes) >= 25


def test_08_source_hashes_correct(report):
    """Every source_sha256 entry must match the SHA-256 of the actual input file."""
    computed = compute_source_hashes()
    reported = report["source_sha256"]
    assert set(reported.keys()) == set(computed.keys())
    for key in computed:
        assert reported[key] == computed[key], f"Hash mismatch for {key}"


def test_09_fixture_integrity():
    """Verify policy.json has not been modified from its expected hash."""
    for rel, expected in FIXTURE_HASHES.items():
        fp = APP / rel
        with open(fp, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        assert actual == expected, f"Fixture {rel} changed"


def test_10_scene_audit_count(report, scenes):
    """Number of scene_audits entries must equal the number of scene input files."""
    assert len(report["scene_audits"]) == len(scenes)


def test_11_scene_audits_sorted(report):
    """scene_audits must be sorted by scene_id in ascending order."""
    sids = [a["scene_id"] for a in report["scene_audits"]]
    assert sids == sorted(sids)


# === POLYGON PROPERTY TESTS ===

def test_12_scene01_rect_area(report):
    """rect_A (10x6 CCW rectangle) must have area=60 and signed_area=60."""
    sa = get_scene_audit(report, "scene_01")
    rect = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "rect_A")
    assert rect["area"] == 60.0
    assert rect["signed_area"] == 60.0


def test_13_scene01_rect_perimeter(report):
    """rect_A perimeter = 2*(10+6) = 32."""
    sa = get_scene_audit(report, "scene_01")
    rect = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "rect_A")
    assert rect["perimeter"] == 32.0


def test_14_scene01_rect_centroid(report):
    """rect_A centroid via shoelace formula must be (5,3)."""
    sa = get_scene_audit(report, "scene_01")
    rect = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "rect_A")
    assert rect["centroid"] == [5.0, 3.0]


def test_15_scene01_rect_properties(report):
    """rect_A must be CCW, convex, and simple."""
    sa = get_scene_audit(report, "scene_01")
    rect = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "rect_A")
    assert rect["orientation"] == "CCW"
    assert rect["is_convex"] is True
    assert rect["is_simple"] is True


def test_16_scene02_lshape_area(report):
    """L_shape polygon area=27, signed_area=27 (CCW winding)."""
    sa = get_scene_audit(report, "scene_02")
    ls = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "L_shape")
    assert ls["area"] == 27.0
    assert ls["signed_area"] == 27.0


def test_17_scene02_lshape_concave(report):
    """L_shape is concave (not convex) but simple, wound CCW."""
    sa = get_scene_audit(report, "scene_02")
    ls = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "L_shape")
    assert ls["is_convex"] is False
    assert ls["is_simple"] is True
    assert ls["orientation"] == "CCW"


def test_18_scene05_cw_orientation(report):
    """CW-wound polygon should have negative signed area."""
    sa = get_scene_audit(report, "scene_05")
    cw = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "cw_square")
    assert cw["signed_area"] < 0
    assert cw["orientation"] == "CW"
    assert cw["area"] == abs(cw["signed_area"])


def test_19_scene05_star_self_intersecting(report):
    """5-pointed star polygon should be detected as self-intersecting AND not convex."""
    sa = get_scene_audit(report, "scene_05")
    star = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "star_5")
    assert star["is_simple"] is False
    assert star["is_convex"] is False, "Self-intersecting polygon cannot be convex"


def test_20_scene04_triangle_properties(report):
    """tri_A must be convex, simple, with area=24."""
    sa = get_scene_audit(report, "scene_04")
    tri = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "tri_A")
    assert tri["is_convex"] is True
    assert tri["is_simple"] is True
    assert abs(tri["area"] - 24.0) < 0.001


# === POINT-IN-POLYGON TESTS ===

def test_21_scene01_pip_inside(report):
    """Query point 0 in scene_01 lies inside rect_A."""
    sa = get_scene_audit(report, "scene_01")
    pip0 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 0)
    assert pip0["result"] == "inside"


def test_22_scene01_pip_outside(report):
    """Query point 1 in scene_01 lies outside rect_A."""
    sa = get_scene_audit(report, "scene_01")
    pip1 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 1)
    assert pip1["result"] == "outside"


def test_23_scene01_pip_boundary_edge(report):
    """Point (10,3) is on the right edge of the rectangle."""
    sa = get_scene_audit(report, "scene_01")
    pip2 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 2)
    assert pip2["result"] == "boundary"


def test_24_scene01_pip_boundary_vertex(report):
    """Point (0,0) is on a vertex of the rectangle."""
    sa = get_scene_audit(report, "scene_01")
    pip3 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 3)
    assert pip3["result"] == "boundary"


def test_25_scene01_pip_boundary_bottom_edge(report):
    """Point (5,0) is on the bottom edge."""
    sa = get_scene_audit(report, "scene_01")
    pip4 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 4)
    assert pip4["result"] == "boundary"


def test_26_scene02_pip_concavity(report):
    """Point (4.5,4.5) is in the concave notch of the L-shape, should be outside."""
    sa = get_scene_audit(report, "scene_02")
    pip2 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 2)
    assert pip2["result"] == "outside"


def test_27_scene02_pip_reflex_vertex(report):
    """Point (3,3) is on the reflex vertex of the L-shape, should be boundary."""
    sa = get_scene_audit(report, "scene_02")
    pip3 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 3)
    assert pip3["result"] == "boundary"


def test_28_scene04_pip_triangle(report):
    """Scene 04 triangle: point 0 is inside, point 3 is on the boundary."""
    sa = get_scene_audit(report, "scene_04")
    pip0 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 0)
    assert pip0["result"] == "inside"
    pip3 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 3)
    assert pip3["result"] == "boundary"


# === CONVEX HULL TESTS ===

def test_29_scene03_hull_excludes_collinear(report):
    """Points (0,0),(2,0),(4,0),(6,0) are collinear. Hull should exclude interior ones.
    Hull must start at lex-smallest point and vertices must be in CCW order."""
    sa = get_scene_audit(report, "scene_03")
    hull = sa["convex_hull"]
    hull_pts = [tuple(v) for v in hull["vertices"]]
    assert (2.0, 0.0) not in hull_pts
    assert (4.0, 0.0) not in hull_pts
    assert (0.0, 0.0) in hull_pts
    assert (6.0, 0.0) in hull_pts
    verts = hull["vertices"]
    lex_min = min(verts, key=lambda p: (p[0], p[1]))
    assert verts[0] == lex_min, "Hull must start at lexicographically smallest point"
    n = len(verts)
    if n >= 3:
        for i in range(n):
            a = verts[i]
            b = verts[(i + 1) % n]
            c = verts[(i + 2) % n]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            assert cross >= -1e-9, f"Hull not in CCW order at index {i}"


def test_30_scene01_hull_vertex_count(report):
    """Hull vertex_count must match len(vertices) and be at least 4 for scene_01."""
    sa = get_scene_audit(report, "scene_01")
    hull = sa["convex_hull"]
    assert hull["vertex_count"] == len(hull["vertices"])
    assert hull["vertex_count"] >= 4


def test_31_scene03_hull_area(report):
    """Scene 03 convex hull area must be 14.0."""
    sa = get_scene_audit(report, "scene_03")
    hull = sa["convex_hull"]
    assert abs(hull["area"] - 14.0) < 0.01


# === SEGMENT INTERSECTION TESTS ===

def test_32_scene01_segment_intersection(report):
    """Scene 01 has exactly 1 segment intersection at (5,3)."""
    sa = get_scene_audit(report, "scene_01")
    ints = sa["segment_intersections"]
    assert len(ints) == 1
    assert abs(ints[0]["point"][0] - 5.0) < 0.001
    assert abs(ints[0]["point"][1] - 3.0) < 0.001


def test_33_scene04_segment_intersections(report):
    """Scene 4 has 5 segments forming triangle edges + cross lines. Should have multiple intersections."""
    sa = get_scene_audit(report, "scene_04")
    ints = sa["segment_intersections"]
    assert len(ints) >= 3


def test_34_scene04_intersections_sorted(report):
    """Segment intersections must be sorted by (segment_a, segment_b)."""
    sa = get_scene_audit(report, "scene_04")
    ints = sa["segment_intersections"]
    for i in range(len(ints) - 1):
        assert (ints[i]["segment_a"], ints[i]["segment_b"]) <= \
               (ints[i+1]["segment_a"], ints[i+1]["segment_b"])


# === CLOSEST PAIR TESTS ===

def test_35_scene06_closest_pair_duplicates(report):
    """Scene 6 has duplicate points at (0,0) and (3,4). Closest pair should be distance 0."""
    sa = get_scene_audit(report, "scene_06")
    cp = sa["closest_pair"]
    assert cp["distance"] == 0.0


def test_36_scene01_closest_pair(report):
    """Scene 01 closest pair must have positive distance and point_a_idx < point_b_idx."""
    sa = get_scene_audit(report, "scene_01")
    cp = sa["closest_pair"]
    assert cp["distance"] > 0
    assert cp["point_a_idx"] < cp["point_b_idx"]


# === MIN ENCLOSING CIRCLE TESTS ===

def test_37_scene01_mec_contains_all(report):
    """Min enclosing circle must contain all points and polygon vertices."""
    sa = get_scene_audit(report, "scene_01")
    mec = sa["min_enclosing_circle"]
    cx, cy = mec["center"]
    r = mec["radius"]
    scene_data = None
    for fn in sorted(os.listdir(SCENES_DIR)):
        if fn.endswith(".json"):
            with open(SCENES_DIR / fn) as f:
                d = json.load(f)
                if d["scene_id"] == "scene_01":
                    scene_data = d
                    break
    all_pts = list(scene_data["points"])
    for poly in scene_data["polygons"]:
        all_pts.extend(poly["vertices"])
    for pt in all_pts:
        d = math.sqrt((pt[0] - cx)**2 + (pt[1] - cy)**2)
        assert d <= r + 0.01, f"Point {pt} outside MEC"


def test_38_scene03_mec_radius(report):
    """Scene 03 MEC must match the true minimum enclosing circle, not just any enclosing circle."""
    sa = get_scene_audit(report, "scene_03")
    mec = sa["min_enclosing_circle"]
    assert mec["radius"] > 0
    assert abs(mec["radius"] - 3.125) < 0.01
    assert abs(mec["center"][0] - 3.0) < 0.01
    assert abs(mec["center"][1] - 0.875) < 0.01


# === DEGENERATE POLYGON TESTS ===

def test_39_scene06_degenerate_line(report):
    """Polygon degen_line has collinear vertices → zero area → degenerate orientation."""
    sa = get_scene_audit(report, "scene_06")
    degen = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "degen_line")
    assert degen["area"] < 1e-6
    assert degen["orientation"] == "degenerate"


def test_40_scene06_degenerate_point(report):
    """Polygon degen_point has all identical vertices → zero area → degenerate orientation."""
    sa = get_scene_audit(report, "scene_06")
    degen = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "degen_point")
    assert degen["area"] < 1e-6
    assert degen["orientation"] == "degenerate"


def test_41_scene06_tiny_triangle(report):
    """tiny_tri has very small but nonzero area."""
    sa = get_scene_audit(report, "scene_06")
    tiny = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "tiny_tri")
    assert tiny["area"] > 0
    assert tiny["area"] < 0.001


# === FINDINGS TESTS ===

def test_42_scene05_self_intersecting_finding(report):
    """star_5 polygon must produce a self_intersecting_polygon finding with critical severity."""
    sa = get_scene_audit(report, "scene_05")
    si = [f for f in sa["findings"] if f["finding_type"] == "self_intersecting_polygon"]
    assert len(si) == 1
    assert si[0]["polygon_id"] == "star_5"
    assert si[0]["severity"] == "critical"


def test_43_scene06_degenerate_findings(report):
    """Scene 06 must flag degen_line and degen_point as degenerate_polygon findings."""
    sa = get_scene_audit(report, "scene_06")
    degen = [f for f in sa["findings"] if f["finding_type"] == "degenerate_polygon"]
    assert len(degen) >= 2
    poly_ids = [f["polygon_id"] for f in degen]
    assert "degen_line" in poly_ids
    assert "degen_point" in poly_ids


def test_44_scene06_duplicate_findings(report):
    """Scene 06 has duplicate standalone points and must produce at least 1 duplicate_points finding."""
    sa = get_scene_audit(report, "scene_06")
    dups = [f for f in sa["findings"] if f["finding_type"] == "duplicate_points"]
    assert len(dups) >= 1


def test_45_findings_severity_order(report, policy):
    """Global findings must be sorted by severity rank (ascending)."""
    sev_ranks = policy["severity_ranks"]
    findings = report["findings"]
    for i in range(len(findings) - 1):
        r1 = sev_ranks.get(findings[i]["severity"], 99)
        r2 = sev_ranks.get(findings[i + 1]["severity"], 99)
        assert r1 <= r2


def test_46_findings_by_type_correct(report):
    """summary.findings_by_type must match counts computed from the findings array."""
    fbt = {}
    for f in report["findings"]:
        fbt[f["finding_type"]] = fbt.get(f["finding_type"], 0) + 1
    assert report["summary"]["findings_by_type"] == fbt


def test_47_findings_by_severity_correct(report):
    """summary.findings_by_severity must match counts computed from the findings array."""
    fbs = {}
    for f in report["findings"]:
        fbs[f["severity"]] = fbs.get(f["severity"], 0) + 1
    reported = report["summary"]["findings_by_severity"]
    for sev in ["critical", "high", "medium", "low", "info"]:
        assert reported.get(sev, 0) == fbs.get(sev, 0)


def test_48_total_findings_count(report):
    """summary.total_findings must equal the sum of per-scene finding counts."""
    per_scene = sum(len(a.get("findings", [])) for a in report["scene_audits"])
    assert report["summary"]["total_findings"] == per_scene


# === CROSS-VALIDATION ===

def test_49_bounding_box_correct(report):
    """rect_A bounding box must span (0,0) to (10,6)."""
    sa = get_scene_audit(report, "scene_01")
    rect = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "rect_A")
    bb = rect["bounding_box"]
    assert bb["min_x"] == 0
    assert bb["min_y"] == 0
    assert bb["max_x"] == 10
    assert bb["max_y"] == 6


def test_50_hull_area_leq_bbox(report):
    """Convex hull area must be <= bounding box area of all points."""
    for sa in report["scene_audits"]:
        if "convex_hull" not in sa:
            continue
        hull = sa["convex_hull"]
        if hull["vertex_count"] < 3:
            continue
        hull_verts = hull["vertices"]
        xs = [v[0] for v in hull_verts]
        ys = [v[1] for v in hull_verts]
        bbox_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        assert hull["area"] <= bbox_area + 0.001


def test_51_scene05_cw_signed_area_exact(report):
    """CW square (0,0)→(0,4)→(4,4)→(4,0) has signed area = -16."""
    sa = get_scene_audit(report, "scene_05")
    cw = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "cw_square")
    assert cw["signed_area"] == -16.0
    assert cw["area"] == 16.0
    assert cw["perimeter"] == 16.0
    assert cw["centroid"] == [2.0, 2.0]


def test_52_scene02_centroid_exact(report):
    """L-shape centroid via shoelace centroid formula: (2.5, 2.5)."""
    sa = get_scene_audit(report, "scene_02")
    ls = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "L_shape")
    assert abs(ls["centroid"][0] - 2.5) < 0.01
    assert abs(ls["centroid"][1] - 2.5) < 0.01


def test_53_scene04_segment_intersection_count(report):
    """Scene 4 has 5 segments (3 triangle edges + horizontal + vertical).
    Exact intersection count should be 9."""
    sa = get_scene_audit(report, "scene_04")
    assert len(sa["segment_intersections"]) == 9


def test_54_closest_pair_standalone_only(report):
    """Scene 01 closest pair must use standalone points only, not polygon vertices.
    Standalone points: (5,3),(12,4),(10,3),(0,0),(5,0).
    Closest: (12,4)-(10,3) = sqrt(5) ≈ 2.236."""
    sa = get_scene_audit(report, "scene_01")
    cp = sa["closest_pair"]
    assert abs(cp["distance"] - 2.236068) < 0.001
    assert cp["point_a_idx"] == 1
    assert cp["point_b_idx"] == 2


def test_55_scene05_cw_square_pip(report):
    """Point (2,2) inside CW-wound square should still be 'inside'."""
    sa = get_scene_audit(report, "scene_05")
    pip0 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 0)
    assert pip0["result"] == "inside"


# === ROUNDING VERIFICATION ===


def test_56_float_rounding_to_output_decimals(report):
    """All non-integer float values must be rounded to output_decimals (6) places."""
    sa = get_scene_audit(report, "scene_01")
    cp = sa["closest_pair"]
    mec = sa["min_enclosing_circle"]
    for val in [cp["distance"], mec["radius"], mec["center"][0], mec["center"][1]]:
        assert val == round(val, 6), f"Value {val} not rounded to 6 decimals"


# === SCENE 07: SELF-INTERSECTING BOWTIE, NEAR-DEGENERATE, CONCAVE CW ===


def test_57_scene07_bowtie_zero_area(report):
    """Bowtie polygon [[0,0],[4,3],[0,3],[4,0]] has edges that cross, creating two
    opposing triangles whose signed areas cancel to exactly zero."""
    sa = get_scene_audit(report, "scene_07")
    bowtie = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "bowtie")
    assert bowtie["signed_area"] == 0.0
    assert bowtie["area"] == 0.0
    assert bowtie["orientation"] == "degenerate"


def test_58_scene07_bowtie_self_intersecting_not_convex(report):
    """Bowtie must be detected as self-intersecting (not simple) and therefore not convex."""
    sa = get_scene_audit(report, "scene_07")
    bowtie = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "bowtie")
    assert bowtie["is_simple"] is False
    assert bowtie["is_convex"] is False


def test_59_scene07_bowtie_dual_findings(report):
    """A self-intersecting polygon with zero area must emit BOTH degenerate_polygon
    AND self_intersecting_polygon findings. These checks are independent."""
    sa = get_scene_audit(report, "scene_07")
    degen = [f for f in sa["findings"]
             if f["finding_type"] == "degenerate_polygon" and f["polygon_id"] == "bowtie"]
    self_int = [f for f in sa["findings"]
                if f["finding_type"] == "self_intersecting_polygon" and f["polygon_id"] == "bowtie"]
    assert len(degen) == 1, "Bowtie must trigger degenerate_polygon"
    assert len(self_int) == 1, "Bowtie must trigger self_intersecting_polygon"
    assert self_int[0]["severity"] == "critical"
    assert degen[0]["severity"] == "high"


def test_60_scene07_bowtie_pip_diagonal_boundary(report):
    """Point (2,1.5) lies exactly on the diagonal edge (0,0)->(4,3) of the bowtie."""
    sa = get_scene_audit(report, "scene_07")
    pip0 = next(p for p in sa["point_in_polygon"]
                if p["point_idx"] == 0 and p["polygon_id"] == "bowtie")
    assert pip0["result"] == "boundary"


def test_61_scene07_bowtie_pip_top_edge_boundary(report):
    """Point (2,3) lies on the horizontal edge of the bowtie at y=3."""
    sa = get_scene_audit(report, "scene_07")
    pip1 = next(p for p in sa["point_in_polygon"]
                if p["point_idx"] == 1 and p["polygon_id"] == "bowtie")
    assert pip1["result"] == "boundary"


def test_62_scene07_bowtie_pip_outside_even_odd(report):
    """Points (0,1.5) and (4,1.5) are outside the bowtie by the even-odd rule.
    Despite appearing near the polygon center, the self-intersection causes
    an even number of crossings."""
    sa = get_scene_audit(report, "scene_07")
    pip2 = next(p for p in sa["point_in_polygon"]
                if p["point_idx"] == 2 and p["polygon_id"] == "bowtie")
    pip3 = next(p for p in sa["point_in_polygon"]
                if p["point_idx"] == 3 and p["polygon_id"] == "bowtie")
    assert pip2["result"] == "outside"
    assert pip3["result"] == "outside"


def test_63_scene07_near_degen_at_threshold(report):
    """near_degen triangle has raw area ≈ 9.99e-7 which is just below min_polygon_area
    (1e-6) due to floating-point arithmetic. Must be flagged as degenerate."""
    sa = get_scene_audit(report, "scene_07")
    nd = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "near_degen")
    assert nd["area"] <= 1e-6
    degen = [f for f in sa["findings"]
             if f["finding_type"] == "degenerate_polygon" and f["polygon_id"] == "near_degen"]
    assert len(degen) == 1, "near_degen must be flagged as degenerate_polygon"


def test_64_scene07_near_degen_pip_inside(report):
    """Point (10.001, 10.0003) is inside the near_degen triangle."""
    sa = get_scene_audit(report, "scene_07")
    pip4 = next(p for p in sa["point_in_polygon"]
                if p["point_idx"] == 4 and p["polygon_id"] == "near_degen")
    assert pip4["result"] == "inside"


def test_65_scene07_chevron_cw_concave(report):
    """Chevron [[0,8],[3,10],[6,8],[3,9]] is CW, concave (not convex), simple, area=3."""
    sa = get_scene_audit(report, "scene_07")
    ch = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "chevron")
    assert ch["orientation"] == "CW"
    assert ch["is_convex"] is False
    assert ch["is_simple"] is True
    assert ch["area"] == 3.0
    assert ch["signed_area"] == -3.0
    assert ch["centroid"] == [3.0, 9.0]


def test_66_scene07_chevron_pip_vertex_boundary(report):
    """Point (3,9) is exactly at the concave vertex of chevron → boundary."""
    sa = get_scene_audit(report, "scene_07")
    pip5 = next(p for p in sa["point_in_polygon"]
                if p["point_idx"] == 5 and p["polygon_id"] == "chevron")
    assert pip5["result"] == "boundary"


def test_67_scene07_chevron_pip_concave_notch(report):
    """Point (3,8.5) is in the concave notch of chevron → outside."""
    sa = get_scene_audit(report, "scene_07")
    pip6 = next(p for p in sa["point_in_polygon"]
                if p["point_idx"] == 6 and p["polygon_id"] == "chevron")
    assert pip6["result"] == "outside"


def test_68_scene07_collinear_overlap_intersection(report):
    """Collinear overlapping segments [0,0]->[6,0] and [2,0]->[8,0] must report
    intersection at [6,0] — the first endpoint of segment_a found on segment_b."""
    sa = get_scene_audit(report, "scene_07")
    ints = sa["segment_intersections"]
    seg01 = next((x for x in ints if x["segment_a"] == 0 and x["segment_b"] == 1), None)
    assert seg01 is not None, "Collinear overlapping segments must produce an intersection"
    assert seg01["point"] == [6.0, 0.0]


def test_69_scene07_segment_intersection_count(report):
    """Scene 07 has exactly 9 segment intersections including the collinear overlap."""
    sa = get_scene_audit(report, "scene_07")
    assert len(sa["segment_intersections"]) == 9


def test_70_scene07_duplicate_points_finding(report):
    """Standalone points at indices 7 and 8 are both (20,20) → duplicate_points finding."""
    sa = get_scene_audit(report, "scene_07")
    dups = [f for f in sa["findings"] if f["finding_type"] == "duplicate_points"]
    assert len(dups) >= 1


def test_71_scene07_total_findings_count(report):
    """Scene 07: 1 self_intersecting (bowtie) + 2 degenerate (bowtie, near_degen) +
    1 duplicate_points = 4 total findings."""
    sa = get_scene_audit(report, "scene_07")
    assert len(sa["findings"]) == 4


def test_72_scene07_findings_severity_order(report, policy):
    """Scene 07 findings must be ordered: critical (self_intersecting) before
    high (degenerate) before low (duplicate_points)."""
    sa = get_scene_audit(report, "scene_07")
    sev_ranks = policy["severity_ranks"]
    findings = sa["findings"]
    for i in range(len(findings) - 1):
        r1 = sev_ranks.get(findings[i]["severity"], 99)
        r2 = sev_ranks.get(findings[i + 1]["severity"], 99)
        assert r1 <= r2, f"Finding {i} severity {findings[i]['severity']} must come before {findings[i+1]['severity']}"


def test_73_scene07_closest_pair_duplicates(report):
    """Closest pair must be the duplicate points (7,8) at distance 0."""
    sa = get_scene_audit(report, "scene_07")
    cp = sa["closest_pair"]
    assert cp["distance"] == 0.0
    assert cp["point_a_idx"] == 7
    assert cp["point_b_idx"] == 8


# === SCENE 08: EPSILON SQUARE, ZIGZAG PIP, CONCAVE ARROW ===


def test_74_scene08_epsilon_square_degenerate(report):
    """epsilon_square with 1e-6 edge length has area ≈ 1e-12 → degenerate."""
    sa = get_scene_audit(report, "scene_08")
    eps = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "epsilon_square")
    assert eps["area"] < 1e-6
    assert eps["orientation"] == "degenerate"
    degen = [f for f in sa["findings"]
             if f["finding_type"] == "degenerate_polygon" and f["polygon_id"] == "epsilon_square"]
    assert len(degen) == 1


def test_75_scene08_epsilon_square_centroid_fallback(report):
    """When signed area < epsilon, centroid must use arithmetic mean of vertices,
    not the shoelace formula (which would divide by near-zero)."""
    sa = get_scene_audit(report, "scene_08")
    eps = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "epsilon_square")
    assert abs(eps["centroid"][0] - 100.0) < 0.001
    assert abs(eps["centroid"][1] - 100.0) < 0.001


def test_76_scene08_zigzag_properties(report):
    """zigzag polygon: area=32, CCW, not convex, simple, centroid at (4, 23/6)."""
    sa = get_scene_audit(report, "scene_08")
    zz = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "zigzag")
    assert zz["area"] == 32.0
    assert zz["signed_area"] == 32.0
    assert zz["orientation"] == "CCW"
    assert zz["is_convex"] is False
    assert zz["is_simple"] is True
    assert zz["centroid"] == [4.0, 3.833333]


def test_77_scene08_concave_arrow_properties(report):
    """concave_arrow: area=37, CW, centroid at (5, 1181/111 ≈ 10.63964)."""
    sa = get_scene_audit(report, "scene_08")
    ca = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "concave_arrow")
    assert ca["area"] == 37.0
    assert ca["signed_area"] == -37.0
    assert ca["orientation"] == "CW"
    assert ca["is_convex"] is False
    assert ca["is_simple"] is True
    assert ca["centroid"][0] == 5.0
    assert abs(ca["centroid"][1] - 10.63964) < 0.00001


def test_78_scene08_zigzag_pip_vertex_at_y0(report):
    """(4,0) is on zigzag vertex → boundary. This is at y=0 where three polygon
    vertices exist, testing precise boundary detection."""
    sa = get_scene_audit(report, "scene_08")
    pip4 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 4)
    assert pip4["result"] == "boundary"


def test_79_scene08_zigzag_pip_outside_at_y0(report):
    """(2,0) and (6,0) are outside zigzag. The horizontal ray at y=0 passes through
    polygon vertices at (0,0), (4,0), and (8,0). Correct half-open interval handling
    required: (yi <= py < yj) or (yj <= py < yi)."""
    sa = get_scene_audit(report, "scene_08")
    pip2 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 2)
    pip3 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 3)
    assert pip2["result"] == "outside", "(2,0) must be outside zigzag"
    assert pip3["result"] == "outside", "(6,0) must be outside zigzag"


def test_80_scene08_zigzag_pip_inside(report):
    """(4,3) and (4,5) are inside the zigzag polygon interior."""
    sa = get_scene_audit(report, "scene_08")
    pip0 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 0)
    pip1 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 1)
    assert pip0["result"] == "inside"
    assert pip1["result"] == "inside"


def test_81_scene08_concave_arrow_pip_vertex_y(report):
    """(5,10) is inside concave_arrow despite y=10 having 4 polygon vertices and
    2 horizontal edges. Tests that horizontal edges produce zero crossings and
    half-open intervals correctly handle vertex clusters."""
    sa = get_scene_audit(report, "scene_08")
    pip6 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 6)
    assert pip6["result"] == "inside"


def test_82_scene08_concave_arrow_pip_inside_shaft(report):
    """(5,12) inside the triangular head, (5,8) inside the rectangular shaft."""
    sa = get_scene_audit(report, "scene_08")
    pip5 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 5)
    pip7 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 7)
    assert pip5["result"] == "inside"
    assert pip7["result"] == "inside"


def test_83_scene08_epsilon_pip_inside(report):
    """(100.0000005, 100.0000005) is inside epsilon_square despite its near-zero area."""
    sa = get_scene_audit(report, "scene_08")
    pip8 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 8)
    assert pip8["result"] == "inside"


def test_84_scene08_segment_intersections_exact(report):
    """Scene 08 vertical segment crosses 4 horizontal/diagonal segments.
    All intersections are at x=4 with y values 0, 3, 4, 6."""
    sa = get_scene_audit(report, "scene_08")
    ints = sa["segment_intersections"]
    assert len(ints) == 4
    ys = sorted([i["point"][1] for i in ints])
    assert ys == [0.0, 3.0, 4.0, 6.0]
    for i in ints:
        assert i["point"][0] == 4.0


def test_85_scene08_closest_pair(report):
    """Closest standalone pair is (0,1) = points (4,3) and (4,5), distance=2.0."""
    sa = get_scene_audit(report, "scene_08")
    cp = sa["closest_pair"]
    assert cp["point_a_idx"] == 0
    assert cp["point_b_idx"] == 1
    assert cp["distance"] == 2.0


def test_86_scene08_single_finding(report):
    """Scene 08 has exactly 1 finding: degenerate epsilon_square."""
    sa = get_scene_audit(report, "scene_08")
    assert len(sa["findings"]) == 1
    assert sa["findings"][0]["finding_type"] == "degenerate_polygon"
    assert sa["findings"][0]["polygon_id"] == "epsilon_square"


def test_87_scene07_bowtie_centroid_arithmetic_mean(report):
    """Bowtie has zero signed area, so centroid must use arithmetic mean:
    ((0+4+0+4)/4, (0+3+3+0)/4) = (2.0, 1.5)."""
    sa = get_scene_audit(report, "scene_07")
    bowtie = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "bowtie")
    assert bowtie["centroid"] == [2.0, 1.5]


def test_88_scene07_bowtie_perimeter(report):
    """Bowtie perimeter = 4 edges each of length 5 (3-4-5 diagonals) minus correction.
    Edges: (0,0)->(4,3)=5, (4,3)->(0,3)=4.XXXX, (0,3)->(4,0)=5, (4,0)->(0,0)=4.XXX.
    Actually: dist((0,0),(4,3))=5, dist((4,3),(0,3))=4, dist((0,3),(4,0))=5, dist((4,0),(0,0))=4.
    Total = 18."""
    sa = get_scene_audit(report, "scene_07")
    bowtie = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "bowtie")
    assert bowtie["perimeter"] == 18.0


def test_89_global_findings_include_new_scenes(report):
    """Global findings must include findings from scene_07 and scene_08."""
    s07_findings = [f for f in report["findings"] if f.get("scene_id") == "scene_07"]
    s08_findings = [f for f in report["findings"] if f.get("scene_id") == "scene_08"]
    assert len(s07_findings) == 4
    assert len(s08_findings) == 1


def test_90_scene08_collinear_hex_convex(report):
    """collinear_hex has collinear consecutive edges (bottom and top are straight lines
    with a midpoint). It is still convex because collinear edges (cross product ~ 0)
    are ignored for the convexity sign check."""
    sa = get_scene_audit(report, "scene_08")
    ch = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "collinear_hex")
    assert ch["is_convex"] is True, "Polygon with collinear edges must still be convex"
    assert ch["is_simple"] is True
    assert ch["area"] == 24.0
    assert ch["orientation"] == "CCW"
    assert ch["centroid"] == [23.0, 22.0]


def test_91_scene08_collinear_hex_no_findings(report):
    """collinear_hex is a normal polygon with area=24, no findings should be generated."""
    sa = get_scene_audit(report, "scene_08")
    hex_findings = [f for f in sa["findings"] if f.get("polygon_id") == "collinear_hex"]
    assert len(hex_findings) == 0


def test_92_scene07_collinear_seg_intersection_specific(report):
    """For collinear overlap seg0=[0,0]->[6,0] and seg1=[2,0]->[8,0]:
    the endpoint fallback must check seg_a endpoints on seg_b first.
    (0,0) is NOT on [2,0]->[8,0]. (6,0) IS on [2,0]->[8,0] → report [6,0].
    An implementation checking seg_b first would report [2,0] instead."""
    sa = get_scene_audit(report, "scene_07")
    ints = sa["segment_intersections"]
    seg01 = next((x for x in ints if x["segment_a"] == 0 and x["segment_b"] == 1), None)
    assert seg01 is not None
    assert seg01["point"][0] == 6.0, "Must be 6.0 (end of seg_a), not 2.0 (start of seg_b)"
    assert seg01["point"][1] == 0.0


# === FINDINGS EVIDENCE STRUCTURE TESTS ===


def test_93_findings_have_evidence_key(report):
    """Every finding (per-scene and global) must have an 'evidence' key
    containing a dict, not a 'details' string or other field name."""
    for sa in report["scene_audits"]:
        for f in sa.get("findings", []):
            assert "evidence" in f, (
                f"Finding {f['finding_type']} in {sa['scene_id']} missing 'evidence' key"
            )
            assert isinstance(f["evidence"], dict), (
                f"Finding evidence must be a dict, got {type(f['evidence']).__name__}"
            )
    for f in report["findings"]:
        assert "evidence" in f, (
            f"Global finding {f['finding_type']} missing 'evidence' key"
        )
        assert isinstance(f["evidence"], dict)


def test_94_finding_keys_exact(report):
    """Each finding must have exactly these 5 keys:
    finding_type, severity, scene_id, polygon_id, evidence."""
    expected_keys = {"finding_type", "severity", "scene_id", "polygon_id", "evidence"}
    for f in report["findings"]:
        assert set(f.keys()) == expected_keys, (
            f"Finding keys {set(f.keys())} != expected {expected_keys}"
        )


def test_95_degenerate_evidence_structure(report):
    """degenerate_polygon evidence must contain 'area' (float) and 'vertex_count' (int)."""
    for f in report["findings"]:
        if f["finding_type"] == "degenerate_polygon":
            ev = f["evidence"]
            assert "area" in ev, "degenerate_polygon evidence missing 'area'"
            assert "vertex_count" in ev, "degenerate_polygon evidence missing 'vertex_count'"
            assert isinstance(ev["area"], (int, float))
            assert isinstance(ev["vertex_count"], int)


def test_96_self_intersecting_evidence_structure(report):
    """self_intersecting_polygon evidence must contain 'polygon_id' (string)."""
    for f in report["findings"]:
        if f["finding_type"] == "self_intersecting_polygon":
            ev = f["evidence"]
            assert "polygon_id" in ev, "self_intersecting evidence missing 'polygon_id'"
            assert isinstance(ev["polygon_id"], str)
            assert ev["polygon_id"] == f["polygon_id"], (
                "evidence.polygon_id must match top-level polygon_id"
            )


def test_97_duplicate_points_evidence_structure(report):
    """duplicate_points evidence must contain 'point' as a [x, y] list."""
    for f in report["findings"]:
        if f["finding_type"] == "duplicate_points":
            ev = f["evidence"]
            assert "point" in ev, "duplicate_points evidence missing 'point'"
            assert isinstance(ev["point"], list) and len(ev["point"]) == 2, (
                "evidence.point must be a [x, y] list"
            )


# === SCENE 09: MULTIPLE DUPLICATE COORDINATES ===


def test_98_scene09_square_properties(report):
    """square_simple: 10x10 CCW square. Area=100, perimeter=40, centroid=(5,5)."""
    sa = get_scene_audit(report, "scene_09")
    sq = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "square_simple")
    assert sq["signed_area"] == 100.0
    assert sq["area"] == 100.0
    assert sq["perimeter"] == 40.0
    assert sq["centroid"] == [5.0, 5.0]
    assert sq["orientation"] == "CCW"
    assert sq["is_convex"] is True
    assert sq["is_simple"] is True


def test_99_scene09_two_duplicate_findings(report):
    """Scene 09 has TWO distinct duplicate coordinates: (10,10) and (20,30).
    The oracle must emit one duplicate_points finding per coordinate, not just one
    overall. This is a critical difference: 2 findings, not 1."""
    sa = get_scene_audit(report, "scene_09")
    dups = [f for f in sa["findings"] if f["finding_type"] == "duplicate_points"]
    assert len(dups) == 2, (
        f"Expected 2 duplicate_points findings (one per coordinate), got {len(dups)}"
    )


def test_100_scene09_duplicate_evidence_coordinates(report):
    """The two duplicate_points findings in scene_09 must have evidence.point
    matching the actual duplicate coordinates [10,10] and [20,30]."""
    sa = get_scene_audit(report, "scene_09")
    dups = [f for f in sa["findings"] if f["finding_type"] == "duplicate_points"]
    coords = sorted([tuple(f["evidence"]["point"]) for f in dups])
    assert coords == [(10.0, 10.0), (20.0, 30.0)], (
        f"Duplicate evidence coordinates {coords} != expected [(10,10), (20,30)]"
    )


def test_101_scene09_hull_vertex_count(report):
    """Scene 09 convex hull must have 4 vertices. Points (10,10), (15,15) are collinear
    with (0,0) and (20,30), so with hull_collinear_rule='exclude' they are removed."""
    sa = get_scene_audit(report, "scene_09")
    hull = sa["convex_hull"]
    assert hull["vertex_count"] == 4
    assert hull["area"] == 250.0


def test_102_scene09_segment_intersection(report):
    """Scene 09 has two crossing segments: [0,0]->[10,10] and [0,10]->[10,0].
    They intersect at (5,5)."""
    sa = get_scene_audit(report, "scene_09")
    ints = sa["segment_intersections"]
    assert len(ints) == 1
    assert ints[0]["point"] == [5.0, 5.0]


def test_103_scene09_closest_pair(report):
    """Closest pair in scene_09 is the duplicate points at indices (0,1), distance=0."""
    sa = get_scene_audit(report, "scene_09")
    cp = sa["closest_pair"]
    assert cp["point_a_idx"] == 0
    assert cp["point_b_idx"] == 1
    assert cp["distance"] == 0.0


def test_104_scene09_pip(report):
    """(5,5) is inside the 10x10 square, (15,15) is outside."""
    sa = get_scene_audit(report, "scene_09")
    pip4 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 4)
    pip5 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 5)
    assert pip4["result"] == "inside"
    assert pip5["result"] == "outside"


def test_105_scene09_no_polygon_findings(report):
    """square_simple has area=100, so no degenerate or self-intersecting findings.
    Only the 2 duplicate_points findings exist."""
    sa = get_scene_audit(report, "scene_09")
    assert len(sa["findings"]) == 2
    assert all(f["finding_type"] == "duplicate_points" for f in sa["findings"])


def test_106_global_total_findings_exact(report):
    """Global findings must total exactly 15: 2 self_intersecting + 8 degenerate + 5 duplicate.
    Scenes 11 and 12 contribute zero findings (neg_tri is normal, threshold_trap is NOT degenerate)."""
    assert report["summary"]["total_findings"] == 15
    fbt = report["summary"]["findings_by_type"]
    assert fbt.get("self_intersecting_polygon") == 2
    assert fbt.get("degenerate_polygon") == 8
    assert fbt.get("duplicate_points") == 5


def test_107_global_duplicate_points_count(report):
    """There must be exactly 5 duplicate_points findings globally:
    scene_06 has 2 (coords (0,0) and (3,4)), scene_07 has 1 (coord (20,20)),
    scene_09 has 2 (coords (10,10) and (20,30))."""
    dup_findings = [f for f in report["findings"] if f["finding_type"] == "duplicate_points"]
    assert len(dup_findings) == 5, (
        f"Expected 5 global duplicate_points findings, got {len(dup_findings)}"
    )


def test_108_total_scenes(report):
    """total_scenes must be 12."""
    assert report["summary"]["total_scenes"] == 12


def test_109_total_polygons(report):
    """Total polygons across all 12 scenes must be 21."""
    assert report["summary"]["total_polygons"] == 21


def test_110_scene06_two_duplicate_findings(report):
    """Scene 06 also has TWO distinct duplicate coordinates: (0,0) and (3,4).
    Must produce 2 duplicate_points findings, not 1."""
    sa = get_scene_audit(report, "scene_06")
    dups = [f for f in sa["findings"] if f["finding_type"] == "duplicate_points"]
    assert len(dups) == 2, (
        f"Scene 06 expected 2 duplicate_points findings, got {len(dups)}"
    )


# === SCENE 10: DEGENERATE-BUT-CCW, COLLINEAR VERTICES, HULL COLLINEAR EXCLUSION ===


def test_111_scene10_slim_trap_ccw_but_degenerate(report):
    """slim_trap has signed area ≈ 8.75e-7, which is ABOVE epsilon (1e-9) → CCW,
    but BELOW min_polygon_area (1e-6) → degenerate_polygon finding.
    This traps models that equate 'degenerate finding' with 'degenerate orientation'."""
    sa = get_scene_audit(report, "scene_10")
    slim = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "slim_trap")
    assert slim["orientation"] == "CCW", (
        "slim_trap orientation must be CCW (|SA| > epsilon) despite being flagged as degenerate"
    )
    degen = [f for f in sa["findings"]
             if f["finding_type"] == "degenerate_polygon" and f["polygon_id"] == "slim_trap"]
    assert len(degen) == 1, "slim_trap must be flagged as degenerate (area < min_polygon_area)"


def test_112_scene10_slim_trap_centroid_shoelace(report):
    """slim_trap centroid MUST use the shoelace formula (since |SA| > epsilon), NOT the
    arithmetic mean fallback. Shoelace gives centroid x ≈ 1.119048, arithmetic mean
    gives x = 1.125. A model that uses mean for all 'degenerate' polygons fails here."""
    sa = get_scene_audit(report, "scene_10")
    slim = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "slim_trap")
    assert abs(slim["centroid"][0] - 1.119048) < 0.0001, (
        f"slim_trap centroid x must be ≈1.119048 (shoelace), got {slim['centroid'][0]}"
    )


def test_113_scene10_all_collinear_degenerate(report):
    """all_collinear polygon has 3 collinear vertices → zero area → degenerate.
    Centroid must be arithmetic mean = (5.0, 10.0)."""
    sa = get_scene_audit(report, "scene_10")
    colli = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "all_collinear")
    assert colli["orientation"] == "degenerate"
    assert colli["area"] == 0.0
    assert colli["centroid"] == [5.0, 10.0]


def test_114_scene10_hull_collinear_exclusion(report):
    """Standalone points (100,100)→(500,500) are collinear on y=x.
    With hull_collinear_rule='exclude', only extremes (100,100) and (500,500) remain
    on the hull. The 3 intermediate points must be excluded. Hull has 4 vertices."""
    sa = get_scene_audit(report, "scene_10")
    hull = sa["convex_hull"]
    assert hull["vertex_count"] == 4
    hull_pts = [tuple(v) for v in hull["vertices"]]
    assert (200.0, 200.0) not in hull_pts, "Collinear interior point (200,200) must be excluded"
    assert (300.0, 300.0) not in hull_pts, "Collinear interior point (300,300) must be excluded"
    assert (400.0, 400.0) not in hull_pts, "Collinear interior point (400,400) must be excluded"


def test_115_scene10_hull_area(report):
    """Scene 10 hull area must be 3000."""
    sa = get_scene_audit(report, "scene_10")
    assert sa["convex_hull"]["area"] == 3000.0


def test_116_scene10_segment_intersections(report):
    """2 intersections: seg0∩seg1 at (3,0) and seg0∩seg2 at (7,0)."""
    sa = get_scene_audit(report, "scene_10")
    ints = sa["segment_intersections"]
    assert len(ints) == 2
    pts = sorted([(i["point"][0], i["point"][1]) for i in ints])
    assert pts == [(3.0, 0.0), (7.0, 0.0)]


def test_117_scene10_pip_inside_slim(report):
    """Point (1, 0.00000025) is inside slim_trap."""
    sa = get_scene_audit(report, "scene_10")
    pip5 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 5)
    assert pip5["result"] == "inside"


def test_118_scene10_two_degenerate_findings(report):
    """Scene 10 has exactly 2 findings: both degenerate_polygon
    (slim_trap and all_collinear). No duplicate or self-intersecting."""
    sa = get_scene_audit(report, "scene_10")
    assert len(sa["findings"]) == 2
    types = [f["finding_type"] for f in sa["findings"]]
    assert all(t == "degenerate_polygon" for t in types)


def test_119_scene10_slim_trap_is_convex(report):
    """slim_trap is a simple convex trapezoid despite being degenerate."""
    sa = get_scene_audit(report, "scene_10")
    slim = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "slim_trap")
    assert slim["is_convex"] is True
    assert slim["is_simple"] is True


def test_120_source_hashes_25_files(report):
    """With 12 scenes, 12 queries, 1 config → 25 source file hashes."""
    assert len(report["source_sha256"]) == 25


# === STRICT STRUCTURAL VALIDATION TESTS ===


def test_121_findings_by_severity_all_five_keys(report):
    """findings_by_severity must contain ALL 5 severity levels: critical, high,
    medium, low, info — even if some have count 0. An implementation that only
    includes non-zero entries will fail."""
    fbs = report["summary"]["findings_by_severity"]
    for sev in ["critical", "high", "medium", "low", "info"]:
        assert sev in fbs, f"findings_by_severity missing '{sev}' key (should be 0)"


def test_122_findings_by_severity_zero_counts(report):
    """medium and info severities must be present with value 0."""
    fbs = report["summary"]["findings_by_severity"]
    assert fbs.get("medium") == 0, "medium severity count must be 0"
    assert fbs.get("info") == 0, "info severity count must be 0"


def test_123_duplicate_points_polygon_id_null(report):
    """Every duplicate_points finding must have polygon_id as JSON null,
    not the string "null", not absent, not an empty string."""
    for f in report["findings"]:
        if f["finding_type"] == "duplicate_points":
            assert f["polygon_id"] is None, (
                f"duplicate_points polygon_id must be null, got {f['polygon_id']!r}"
            )


def test_124_global_findings_sort_includes_scene_id(report, policy):
    """Global findings must be sorted by (severity_rank, finding_type, scene_id,
    polygon_id). An implementation that omits scene_id from the sort key will
    produce incorrect ordering when two findings share type and severity but
    differ in scene."""
    sev_ranks = policy["severity_ranks"]
    findings = report["findings"]
    for i in range(len(findings) - 1):
        a, b = findings[i], findings[i + 1]
        key_a = (sev_ranks.get(a["severity"], 99), a["finding_type"],
                 a.get("scene_id", ""), a.get("polygon_id", "") or "")
        key_b = (sev_ranks.get(b["severity"], 99), b["finding_type"],
                 b.get("scene_id", ""), b.get("polygon_id", "") or "")
        assert key_a <= key_b, (
            f"Global finding {i} sort key {key_a} > next {key_b}"
        )


def test_125_schema_version_integer_type(report):
    """schema_version must be an integer, not a float (1.0) or string ('1')."""
    assert isinstance(report["schema_version"], int), (
        f"schema_version type must be int, got {type(report['schema_version']).__name__}"
    )


# === SCENE 11: NEGATIVE COORDINATES, CLOSEST PAIR TIES, FRACTIONAL INTERSECTIONS ===


def test_126_scene11_neg_tri_area(report):
    """neg_tri: isosceles triangle in negative coords. area=18, signed_area=18."""
    sa = get_scene_audit(report, "scene_11")
    tri = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "neg_tri")
    assert tri["area"] == 18.0
    assert tri["signed_area"] == 18.0


def test_127_scene11_neg_tri_properties(report):
    """neg_tri: CCW, convex, simple."""
    sa = get_scene_audit(report, "scene_11")
    tri = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "neg_tri")
    assert tri["orientation"] == "CCW"
    assert tri["is_convex"] is True
    assert tri["is_simple"] is True


def test_128_scene11_neg_tri_centroid(report):
    """neg_tri centroid must be (-3.0, 0.0) via shoelace formula.
    Tests correct handling of negative coordinate centroids."""
    sa = get_scene_audit(report, "scene_11")
    tri = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "neg_tri")
    assert tri["centroid"] == [-3.0, 0.0]


def test_129_scene11_neg_tri_perimeter(report):
    """neg_tri perimeter = 6 + 2*sqrt(45) ≈ 19.416408."""
    sa = get_scene_audit(report, "scene_11")
    tri = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "neg_tri")
    assert abs(tri["perimeter"] - 19.416408) < 0.0001


def test_130_scene11_neg_tri_bounding_box(report):
    """neg_tri bounding box spans negative coordinates."""
    sa = get_scene_audit(report, "scene_11")
    tri = next(p for p in sa["polygon_properties"] if p["polygon_id"] == "neg_tri")
    bb = tri["bounding_box"]
    assert bb["min_x"] == -6
    assert bb["min_y"] == -2
    assert bb["max_x"] == 0
    assert bb["max_y"] == 4


def test_131_scene11_closest_pair_tiebreaking(report):
    """Scene 11 has 4 point pairs all at distance 3.0: (0,1), (0,2), (0,3), (0,4).
    Tiebreaker must pick the lexicographically smallest pair (0,1)."""
    sa = get_scene_audit(report, "scene_11")
    cp = sa["closest_pair"]
    assert cp["distance"] == 3.0
    assert cp["point_a_idx"] == 0
    assert cp["point_b_idx"] == 1


def test_132_scene11_pip_outside_origin(report):
    """Point (0,0) is outside neg_tri [(-6,-2),(0,-2),(-3,4)].
    The origin lies to the right of the triangle despite sharing
    a vertex x-coordinate."""
    sa = get_scene_audit(report, "scene_11")
    pip0 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 0)
    assert pip0["result"] == "outside"


def test_133_scene11_pip_inside_negative(report):
    """Point (-3,0) is inside neg_tri. Tests correct PIP for negative coordinates."""
    sa = get_scene_audit(report, "scene_11")
    pip3 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 3)
    assert pip3["result"] == "inside"


def test_134_scene11_pip_outside_below(report):
    """Point (0,-3) is outside neg_tri (below the triangle)."""
    sa = get_scene_audit(report, "scene_11")
    pip4 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 4)
    assert pip4["result"] == "outside"


def test_135_scene11_seg_fractional_intersection(report):
    """Segment (0,2) intersection at (2/3, 2) = (0.666667, 2.0).
    Tests correct rounding of repeating decimal 0.666666... to 6 places."""
    sa = get_scene_audit(report, "scene_11")
    ints = sa["segment_intersections"]
    seg02 = next((x for x in ints if x["segment_a"] == 0 and x["segment_b"] == 2), None)
    assert seg02 is not None, "Segments 0 and 2 must intersect"
    assert seg02["point"] == [0.666667, 2.0], (
        f"Expected [0.666667, 2.0], got {seg02['point']}"
    )


def test_136_scene11_seg_intersection_0_1(report):
    """Segment (0,1) intersection at (0.75, 2.25)."""
    sa = get_scene_audit(report, "scene_11")
    ints = sa["segment_intersections"]
    seg01 = next((x for x in ints if x["segment_a"] == 0 and x["segment_b"] == 1), None)
    assert seg01 is not None
    assert seg01["point"] == [0.75, 2.25]


def test_137_scene11_three_intersections(report):
    """Scene 11 has exactly 3 segment intersections."""
    sa = get_scene_audit(report, "scene_11")
    assert len(sa["segment_intersections"]) == 3


def test_138_scene11_hull(report):
    """Scene 11 convex hull has 5 vertices, area=278.5."""
    sa = get_scene_audit(report, "scene_11")
    hull = sa["convex_hull"]
    assert hull["vertex_count"] == 5
    assert hull["area"] == 278.5


def test_139_scene11_mec(report):
    """Scene 11 MEC must enclose the outlier (50,50) along with all polygon vertices."""
    sa = get_scene_audit(report, "scene_11")
    mec = sa["min_enclosing_circle"]
    assert abs(mec["radius"] - 38.209946) < 0.001


def test_140_scene11_zero_findings(report):
    """Scene 11 has 0 findings. neg_tri is normal (area=18, simple, no duplicates)."""
    sa = get_scene_audit(report, "scene_11")
    assert len(sa["findings"]) == 0


# === SCENE 12: THRESHOLD POLYGON, CLEAN HEXAGON, ZERO FINDINGS ===


def test_141_scene12_threshold_trap_not_degenerate(report):
    """threshold_trap has raw area ≈ 1.05e-6, which is ABOVE min_polygon_area (1e-6).
    Despite the rounded area displaying as 0.000001 (exactly 1e-6), the raw value
    is 1.05e-6 and the check uses raw: 1.05e-6 < 1e-6 = False → NOT degenerate.
    Agents using <= instead of <, or rounding before comparing, will fail."""
    sa = get_scene_audit(report, "scene_12")
    thresh = next(p for p in sa["polygon_properties"]
                  if p["polygon_id"] == "threshold_trap")
    assert thresh["area"] <= 1e-6
    degen = [f for f in sa["findings"]
             if f["finding_type"] == "degenerate_polygon"
             and f["polygon_id"] == "threshold_trap"]
    assert len(degen) == 0, (
        "threshold_trap must NOT be flagged as degenerate (area 1.05e-6 > 1e-6)"
    )


def test_142_scene12_threshold_trap_orientation_ccw(report):
    """threshold_trap orientation must be CCW (|SA| ≈ 1.05e-6 > epsilon 1e-9)."""
    sa = get_scene_audit(report, "scene_12")
    thresh = next(p for p in sa["polygon_properties"]
                  if p["polygon_id"] == "threshold_trap")
    assert thresh["orientation"] == "CCW", (
        "threshold_trap must be CCW, not degenerate"
    )


def test_143_scene12_threshold_trap_centroid_shoelace(report):
    """threshold_trap centroid x must be ≈2.238095 (shoelace formula), NOT 2.25
    (arithmetic mean). Since |SA| > epsilon, centroid must use the shoelace formula.
    An agent that uses arithmetic mean for all tiny polygons fails here."""
    sa = get_scene_audit(report, "scene_12")
    thresh = next(p for p in sa["polygon_properties"]
                  if p["polygon_id"] == "threshold_trap")
    assert abs(thresh["centroid"][0] - 2.238095) < 0.0001, (
        f"threshold_trap centroid x must be ~2.238095 (shoelace), got {thresh['centroid'][0]}"
    )
    assert thresh["centroid"][0] != 2.25, (
        "centroid x=2.25 indicates arithmetic mean was used instead of shoelace"
    )


def test_144_scene12_clean_hex_properties(report):
    """clean_hex: regular hexagon, area=36, CCW, convex, simple."""
    sa = get_scene_audit(report, "scene_12")
    ch = next(p for p in sa["polygon_properties"]
              if p["polygon_id"] == "clean_hex")
    assert ch["area"] == 36.0
    assert ch["signed_area"] == 36.0
    assert ch["orientation"] == "CCW"
    assert ch["is_convex"] is True
    assert ch["is_simple"] is True
    assert ch["centroid"] == [12.0, 13.0]


def test_145_scene12_clean_hex_perimeter(report):
    """clean_hex perimeter = 2*4 + 4*sqrt(13) ≈ 22.422205."""
    sa = get_scene_audit(report, "scene_12")
    ch = next(p for p in sa["polygon_properties"]
              if p["polygon_id"] == "clean_hex")
    assert abs(ch["perimeter"] - 22.422205) < 0.0001


def test_146_scene12_pip_inside_hex(report):
    """Point (12,13) is inside clean_hex (at the centroid)."""
    sa = get_scene_audit(report, "scene_12")
    pip0 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 0)
    assert pip0["result"] == "inside"


def test_147_scene12_pip_inside_threshold(report):
    """Point (2, 0.00000015) is inside threshold_trap despite its near-zero height."""
    sa = get_scene_audit(report, "scene_12")
    pip1 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 1)
    assert pip1["result"] == "inside"


def test_148_scene12_pip_outside_hex(report):
    """Point (20,20) is outside clean_hex."""
    sa = get_scene_audit(report, "scene_12")
    pip2 = next(p for p in sa["point_in_polygon"] if p["point_idx"] == 2)
    assert pip2["result"] == "outside"


def test_149_scene12_zero_findings(report):
    """Scene 12 has exactly 0 findings. threshold_trap is NOT degenerate
    (area > min_polygon_area), clean_hex is normal, no duplicates."""
    sa = get_scene_audit(report, "scene_12")
    assert len(sa["findings"]) == 0, (
        f"Expected 0 findings in scene_12, got {len(sa['findings'])}"
    )


def test_150_scene12_segment_intersection(report):
    """Two diagonal segments cross at (8, 8)."""
    sa = get_scene_audit(report, "scene_12")
    ints = sa["segment_intersections"]
    assert len(ints) == 1
    assert ints[0]["point"] == [8.0, 8.0]


def test_151_scene12_hull(report):
    """Scene 12 hull has 7 vertices and area=122."""
    sa = get_scene_audit(report, "scene_12")
    hull = sa["convex_hull"]
    assert hull["vertex_count"] == 7
    assert hull["area"] == 122.0


def test_152_scene12_threshold_trap_convex_simple(report):
    """threshold_trap is a convex simple trapezoid."""
    sa = get_scene_audit(report, "scene_12")
    thresh = next(p for p in sa["polygon_properties"]
                  if p["polygon_id"] == "threshold_trap")
    assert thresh["is_convex"] is True
    assert thresh["is_simple"] is True


def test_153_scene12_closest_pair(report):
    """Closest pair in scene_12 is (0,2) at distance sqrt(113) ≈ 10.630146."""
    sa = get_scene_audit(report, "scene_12")
    cp = sa["closest_pair"]
    assert cp["point_a_idx"] == 0
    assert cp["point_b_idx"] == 2
    assert abs(cp["distance"] - 10.630146) < 0.001


def test_154_scene12_mec(report):
    """Scene 12 MEC radius ≈ 14.142136 (10*sqrt(2))."""
    sa = get_scene_audit(report, "scene_12")
    mec = sa["min_enclosing_circle"]
    assert abs(mec["radius"] - 14.142136) < 0.001


def test_155_scene12_threshold_trap_bounding_box(report):
    """threshold_trap bounding box: min_x=0, min_y=0, max_x=4, max_y near zero."""
    sa = get_scene_audit(report, "scene_12")
    thresh = next(p for p in sa["polygon_properties"]
                  if p["polygon_id"] == "threshold_trap")
    bb = thresh["bounding_box"]
    assert bb["min_x"] == 0
    assert bb["min_y"] == 0
    assert bb["max_x"] == 4
    assert bb["max_y"] < 0.001


def test_156_all_scenes_present(report):
    """All 12 scene_ids must be present in scene_audits."""
    sids = {a["scene_id"] for a in report["scene_audits"]}
    for i in range(1, 13):
        expected = f"scene_{i:02d}"
        assert expected in sids, f"Missing scene_audit for {expected}"


def test_157_polygon_vertex_count_integer(report):
    """Every polygon vertex_count must be an integer, not a float."""
    for sa in report["scene_audits"]:
        for pp in sa.get("polygon_properties", []):
            assert isinstance(pp["vertex_count"], int), (
                f"{pp['polygon_id']} vertex_count must be int"
            )


def test_158_hull_vertex_count_matches_len(report):
    """For every scene, hull vertex_count must equal len(hull vertices)."""
    for sa in report["scene_audits"]:
        if "convex_hull" not in sa:
            continue
        hull = sa["convex_hull"]
        assert hull["vertex_count"] == len(hull["vertices"]), (
            f"{sa['scene_id']} hull vertex_count != len(vertices)"
        )


def test_159_hull_starts_at_lex_smallest(report):
    """For every scene with a hull, vertices[0] must be the lex-smallest point."""
    for sa in report["scene_audits"]:
        if "convex_hull" not in sa:
            continue
        verts = sa["convex_hull"]["vertices"]
        if len(verts) < 2:
            continue
        lex_min = min(verts, key=lambda p: (p[0], p[1]))
        assert verts[0] == lex_min, (
            f"{sa['scene_id']} hull must start at lex-smallest {lex_min}, "
            f"starts at {verts[0]}"
        )


def test_160_every_finding_has_scene_id(report):
    """Every finding (both per-scene and global) must have a scene_id field."""
    for f in report["findings"]:
        assert "scene_id" in f, f"Global finding missing scene_id: {f}"
    for sa in report["scene_audits"]:
        for f in sa.get("findings", []):
            assert "scene_id" in f, (
                f"Per-scene finding in {sa['scene_id']} missing scene_id"
            )
