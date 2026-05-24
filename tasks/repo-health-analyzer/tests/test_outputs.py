"""Tests for js-repo-health-analyzer-hard."""
import json
import math
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

FLOAT_TOL = 1e-4


def load_report():
    """Load and return parsed JSON from the output file."""
    p = OUT_DIR / "repo_health_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def report():
    """Session-scoped fixture for the report data."""
    return load_report()


def _file(report, path):
    """Helper to find a file entry by path."""
    for f in report["files"]:
        if f["path"] == path:
            return f
    pytest.fail(f"File {path} not found in report")


def _author(report, email):
    """Helper to find an author entry by canonical email."""
    for a in report["authors"]:
        if a["canonical_email"] == email:
            return a
    pytest.fail(f"Author {email} not found in report")


# ── Output format ────────────────────────────────────────────────────────


def test_output_file_exists():
    """Verify the main output file was created."""
    assert (OUT_DIR / "repo_health_report.json").is_file()


def test_json_trailing_newline():
    """Verify output ends with exactly one trailing newline."""
    raw = (OUT_DIR / "repo_health_report.json").read_bytes()
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")


def test_json_two_space_indent():
    """Verify output uses 2-space indentation throughout."""
    text = (OUT_DIR / "repo_health_report.json").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if indent > 0:
            assert indent % 2 == 0, f"Non-2-space indent: {line!r}"


def test_json_sorted_keys(report):
    """Verify all object keys are sorted alphabetically at every nesting level."""
    def check(obj, path="root"):
        if isinstance(obj, dict):
            keys = list(obj.keys())
            assert keys == sorted(keys), f"Unsorted at {path}: {keys}"
            for k, v in obj.items():
                check(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check(item, f"{path}[{i}]")
    check(report)


def test_top_level_keys(report):
    """Verify the report has exactly the required top-level keys."""
    expected = {"metadata", "authors", "author_statistics", "branches",
                "commit_depths", "files", "review_coverage"}
    assert set(report.keys()) == expected


# ── Metadata ─────────────────────────────────────────────────────────────


def test_metadata_analysis_date(report):
    """Verify analysis_date from config."""
    assert report["metadata"]["analysis_date"] == "2025-06-15T00:00:00Z"


def test_metadata_default_branch(report):
    """Verify default_branch from config."""
    assert report["metadata"]["default_branch"] == "main"


def test_metadata_total_commits(report):
    """Verify total commit count is 15."""
    assert report["metadata"]["total_commits"] == 15


def test_metadata_total_authors(report):
    """Verify 4 authors after transitive mailmap normalization."""
    assert report["metadata"]["total_authors"] == 4


def test_metadata_total_authors_not_5(report):
    """Verify not 5 authors (transitive mailmap failure)."""
    assert report["metadata"]["total_authors"] != 5, (
        "Got 5 authors; charlie.p@uni.edu must resolve transitively through "
        "charlie.park@research.io to charlie@example.com"
    )


def test_metadata_total_files(report):
    """Verify 16 files (binaries with churn < min_churn excluded)."""
    assert report["metadata"]["total_files"] == 16


def test_metadata_total_files_not_18(report):
    """Verify not 18 files (min_churn filter must exclude low-churn binaries)."""
    assert report["metadata"]["total_files"] != 18, (
        "Got 18; files with total_churn < config.min_churn (15) must be excluded"
    )


# ── Commit depths ────────────────────────────────────────────────────────


def test_depth_root_f3a1b7c0(report):
    """Verify root commit depth is 0."""
    assert report["commit_depths"]["f3a1b7c0"] == 0


def test_depth_orphan_1c9a5d80(report):
    """Verify orphan root depth is 0."""
    assert report["commit_depths"]["1c9a5d80"] == 0


def test_depth_8d2e4f19(report):
    """Verify linear chain commit depth 1."""
    assert report["commit_depths"]["8d2e4f19"] == 1


def test_depth_b5c9d3e2(report):
    """Verify linear chain commit depth 2."""
    assert report["commit_depths"]["b5c9d3e2"] == 2


def test_depth_1a7f2b84(report):
    """Verify linear chain commit depth 3."""
    assert report["commit_depths"]["1a7f2b84"] == 3


def test_depth_e4d6c8a5(report):
    """Verify commit depth 4."""
    assert report["commit_depths"]["e4d6c8a5"] == 4


def test_depth_4e6f8b31(report):
    """Verify feature branch start depth 3."""
    assert report["commit_depths"]["4e6f8b31"] == 3


def test_depth_a2d7c9e4(report):
    """Verify feature branch middle depth 4."""
    assert report["commit_depths"]["a2d7c9e4"] == 4


def test_depth_6b3a1f56(report):
    """Verify feature branch tip depth 5."""
    assert report["commit_depths"]["6b3a1f56"] == 5


def test_depth_merge_9f5b1d72(report):
    """Verify 2-parent merge: max(4,5)+1=6."""
    assert report["commit_depths"]["9f5b1d72"] == 6


def test_depth_c9e2d4a7(report):
    """Verify post-merge depth 7."""
    assert report["commit_depths"]["c9e2d4a7"] == 7


def test_depth_3f7b5c18(report):
    """Verify post-merge depth 8."""
    assert report["commit_depths"]["3f7b5c18"] == 8


def test_depth_5a1d8e63(report):
    """Verify feature-api tip depth 9."""
    assert report["commit_depths"]["5a1d8e63"] == 9


def test_depth_octopus_7b4d9f20(report):
    """Verify octopus merge uses second-highest parent depth."""
    d = report["commit_depths"]["7b4d9f20"]
    assert d == 7, (
        f"Octopus merge (parents: depths 6,9,0) must use second-highest "
        f"(6)+1=7, got {d}"
    )


def test_depth_final_d1a5e7c3(report):
    """Verify final commit after octopus has depth 8."""
    assert report["commit_depths"]["d1a5e7c3"] == 8


def test_depth_count(report):
    """Verify all 15 commits have depth entries."""
    assert len(report["commit_depths"]) == 15


# ── Authors — transitive mailmap + merge 0.5 weight ──────────────────────


def test_author_count(report):
    """Verify 4 authors after transitive normalization."""
    assert len(report["authors"]) == 4


def test_author_order(report):
    """Verify sort: commit_count desc, first_commit asc, name asc."""
    names = [a["name"] for a in report["authors"]]
    assert names == ["Alice Chen", "Bob Smith", "Charlie Park", "Dana Evans"]


def test_alice_commit_count(report):
    """Verify Alice: 4*1.0 + 1*0.5 = 4.5."""
    assert report["authors"][0]["commit_count"] == 4.5


def test_alice_merge_count(report):
    """Verify Alice has 1 merge commit."""
    assert report["authors"][0]["merge_count"] == 1


def test_alice_email(report):
    """Verify ACHEN@Corp.Dev normalized via mailmap."""
    assert report["authors"][0]["canonical_email"] == "alice@example.com"


def test_alice_files_touched(report):
    """Verify Alice touched 7 unique files."""
    assert report["authors"][0]["files_touched"] == 7


def test_alice_additions(report):
    """Verify Alice raw total_additions."""
    assert report["authors"][0]["total_additions"] == 323


def test_alice_deletions(report):
    """Verify Alice raw total_deletions."""
    assert report["authors"][0]["total_deletions"] == 26


def test_bob_commit_count(report):
    """Verify Bob: 4*1.0 + 1*0.5 = 4.5."""
    assert report["authors"][1]["commit_count"] == 4.5


def test_bob_email(report):
    """Verify bob.smith@old.dev maps correctly."""
    assert report["authors"][1]["canonical_email"] == "bob@example.com"


def test_bob_files_touched(report):
    """Verify Bob touched 10 unique files across aliases."""
    assert report["authors"][1]["files_touched"] == 10


def test_bob_additions(report):
    """Verify Bob raw total_additions."""
    assert report["authors"][1]["total_additions"] == 377


def test_bob_deletions(report):
    """Verify Bob raw total_deletions."""
    assert report["authors"][1]["total_deletions"] == 46


def test_charlie_commit_count(report):
    """Verify Charlie has 3.0 (transitive mailmap resolves all 3 commits)."""
    assert report["authors"][2]["commit_count"] == 3


def test_charlie_email_transitive(report):
    """Verify charlie.p@uni.edu resolves transitively to charlie@example.com."""
    a = _author(report, "charlie@example.com")
    assert a["commit_count"] == 3, (
        "charlie.p@uni.edu -> charlie.park@research.io -> charlie@example.com; "
        "must resolve transitively to get all 3 commits"
    )


def test_charlie_files_touched(report):
    """Verify Charlie touched 6 files across all 3 transitively-resolved commits."""
    assert _author(report, "charlie@example.com")["files_touched"] == 6


def test_charlie_additions(report):
    """Verify Charlie raw additions."""
    assert report["authors"][2]["total_additions"] == 352


def test_no_phantom_author(report):
    """Verify no phantom intermediate mailmap author."""
    emails = [a["canonical_email"] for a in report["authors"]]
    assert "charlie.park@research.io" not in emails


def test_dana_commit_count(report):
    """Verify Dana has 2.0."""
    assert report["authors"][3]["commit_count"] == 2


def test_dana_additions(report):
    """Verify Dana raw additions."""
    assert report["authors"][3]["total_additions"] == 75


# ── Author statistics — population stddev ────────────────────────────────


def test_mean_commits(report):
    """Verify mean: (4.5+4.5+3+2)/4=3.5."""
    assert math.isclose(report["author_statistics"]["mean_commits"], 3.5, abs_tol=FLOAT_TOL)


def test_stddev_population(report):
    """Verify population stddev (N divisor), not sample (N-1)."""
    expected = math.sqrt(
        ((4.5-3.5)**2 + (4.5-3.5)**2 + (3-3.5)**2 + (2-3.5)**2) / 4
    )
    got = report["author_statistics"]["stddev_commits"]
    assert math.isclose(got, expected, abs_tol=FLOAT_TOL)
    wrong_sample = math.sqrt(
        ((4.5-3.5)**2 + (4.5-3.5)**2 + (3-3.5)**2 + (2-3.5)**2) / 3
    )
    assert not math.isclose(got, wrong_sample, abs_tol=FLOAT_TOL), (
        "Got sample stddev; must use population stddev (divide by N)"
    )


def test_median_commits(report):
    """Verify median of [2,3,4.5,4.5]=3.75."""
    assert math.isclose(report["author_statistics"]["median_commits"], 3.75, abs_tol=FLOAT_TOL)


# ── Files — selective decay + feedback + min_churn + 3-level sort ────────


def test_file_count(report):
    """Verify 16 files (after min_churn exclusion)."""
    assert len(report["files"]) == 16


def test_file_sort_order(report):
    """Verify files sorted hotspot desc / total_churn desc / path asc."""
    files = report["files"]
    for i in range(len(files) - 1):
        a, b = files[i], files[i + 1]
        if a["hotspot_score"] != b["hotspot_score"]:
            assert a["hotspot_score"] > b["hotspot_score"]
        elif a["total_churn"] != b["total_churn"]:
            assert a["total_churn"] > b["total_churn"]
        else:
            assert a["path"] <= b["path"]


def test_binary_excluded(report):
    """Verify binary files with churn < min_churn are excluded."""
    paths = [f["path"] for f in report["files"]]
    assert "assets/logo.png" not in paths, (
        "assets/logo.png must be excluded: churn < min_churn (15)"
    )
    assert "assets/banner.jpg" not in paths, (
        "assets/banner.jpg must be excluded: churn < min_churn (15)"
    )


def test_api_js_churn(report):
    """Verify src/api.js churn with selective decay: 232."""
    assert _file(report, "src/api.js")["total_churn"] == 232


def test_api_js_churn_not_221(report):
    """Verify src/api.js churn is not 221 (non-selective decay)."""
    assert _file(report, "src/api.js")["total_churn"] != 221, (
        "Got 221; decay must exempt files modified in the current commit"
    )


def test_api_js_churn_not_272(report):
    """Verify src/api.js churn is not 272 (no global decay at all)."""
    assert _file(report, "src/api.js")["total_churn"] != 272


def test_api_js_churn_not_199(report):
    """Verify src/api.js churn is not raw 199 (no depth weighting)."""
    assert _file(report, "src/api.js")["total_churn"] != 199


def test_api_js_hotspot(report):
    """Verify src/api.js hotspot: 222."""
    assert _file(report, "src/api.js")["hotspot_score"] == 222


def test_api_js_days(report):
    """Verify days_since_last_change is floored integer."""
    f = _file(report, "src/api.js")
    assert f["days_since_last_change"] == 65
    assert isinstance(f["days_since_last_change"], int)


def test_readme_churn(report):
    """Verify README.md churn: 83."""
    assert _file(report, "README.md")["total_churn"] == 83


def test_readme_hotspot(report):
    """Verify README.md hotspot: 120."""
    assert _file(report, "README.md")["hotspot_score"] == 120


def test_index_js_churn(report):
    """Verify src/index.js churn: 99."""
    assert _file(report, "src/index.js")["total_churn"] == 99


def test_index_js_hotspot(report):
    """Verify src/index.js hotspot: 94."""
    assert _file(report, "src/index.js")["hotspot_score"] == 94


def test_auth_js_churn(report):
    """Verify src/auth.js churn: 153."""
    assert _file(report, "src/auth.js")["total_churn"] == 153


def test_auth_js_hotspot(report):
    """Verify src/auth.js hotspot: 70."""
    assert _file(report, "src/auth.js")["hotspot_score"] == 70


def test_experiment_js_churn(report):
    """Verify src/experiment.js churn decayed to 109."""
    assert _file(report, "src/experiment.js")["total_churn"] == 109


def test_experiment_js_churn_not_150(report):
    """Verify experiment.js not 150 (must apply global decay)."""
    assert _file(report, "src/experiment.js")["total_churn"] != 150


def test_experiment_js_hotspot(report):
    """Verify src/experiment.js hotspot: 41."""
    assert _file(report, "src/experiment.js")["hotspot_score"] == 41


def test_crypto_churn(report):
    """Verify src/crypto.js churn: 65."""
    assert _file(report, "src/crypto.js")["total_churn"] == 65


def test_crypto_hotspot(report):
    """Verify src/crypto.js hotspot: 28."""
    assert _file(report, "src/crypto.js")["hotspot_score"] == 28


def test_pagination_before_config(report):
    """Verify pagination.js (22,65) sorts before config.js (22,40) by churn tiebreak."""
    files = report["files"]
    pag_idx = next(i for i, f in enumerate(files) if f["path"] == "src/pagination.js")
    cfg_idx = next(i for i, f in enumerate(files) if f["path"] == "src/config.js")
    assert pag_idx < cfg_idx, (
        "Tied hotspot 22: pagination (churn 65) must sort before config (churn 40)"
    )


def test_pagination_churn(report):
    """Verify src/pagination.js churn: 65."""
    assert _file(report, "src/pagination.js")["total_churn"] == 65


def test_pagination_hotspot(report):
    """Verify src/pagination.js hotspot: 22."""
    assert _file(report, "src/pagination.js")["hotspot_score"] == 22


def test_config_js_churn(report):
    """Verify src/config.js churn: 40."""
    assert _file(report, "src/config.js")["total_churn"] == 40


def test_config_js_hotspot(report):
    """Verify src/config.js hotspot: 22."""
    assert _file(report, "src/config.js")["hotspot_score"] == 22


def test_config_js_distinct_authors(report):
    """Verify src/config.js has 2 distinct authors (zero-change entry still counts)."""
    assert _file(report, "src/config.js")["distinct_authors"] == 2


def test_config_js_last_change(report):
    """Verify config.js last_change_date updated by zero-change commit."""
    assert _file(report, "src/config.js")["last_change_date"] == "2025-02-20T10:00:00Z"


def test_store_churn(report):
    """Verify src/store.js churn: 95."""
    assert _file(report, "src/store.js")["total_churn"] == 95


def test_store_churn_not_93(report):
    """Verify store.js not 93 (non-selective decay)."""
    assert _file(report, "src/store.js")["total_churn"] != 93, (
        "Got 93; decay must exempt files modified in the current commit"
    )


def test_store_hotspot(report):
    """Verify src/store.js hotspot: 21."""
    assert _file(report, "src/store.js")["hotspot_score"] == 21


def test_api_guide_churn(report):
    """Verify docs/API_GUIDE.md churn: 54."""
    assert _file(report, "docs/API_GUIDE.md")["total_churn"] == 54


def test_api_guide_hotspot(report):
    """Verify docs/API_GUIDE.md hotspot: 18."""
    assert _file(report, "docs/API_GUIDE.md")["hotspot_score"] == 18


def test_api_test_churn(report):
    """Verify tests/api.test.js churn: 61."""
    assert _file(report, "tests/api.test.js")["total_churn"] == 61


def test_api_test_hotspot(report):
    """Verify tests/api.test.js hotspot: 17."""
    assert _file(report, "tests/api.test.js")["hotspot_score"] == 17


def test_auth_test_churn(report):
    """Verify tests/auth.test.js churn: 70."""
    assert _file(report, "tests/auth.test.js")["total_churn"] == 70


def test_auth_test_hotspot(report):
    """Verify tests/auth.test.js hotspot: 15."""
    assert _file(report, "tests/auth.test.js")["hotspot_score"] == 15


def test_architecture_churn(report):
    """Verify docs/ARCHITECTURE.md churn: 59."""
    assert _file(report, "docs/ARCHITECTURE.md")["total_churn"] == 59


def test_architecture_hotspot(report):
    """Verify docs/ARCHITECTURE.md hotspot: 14."""
    assert _file(report, "docs/ARCHITECTURE.md")["hotspot_score"] == 14


def test_utils_churn(report):
    """Verify src/utils.js churn: 64."""
    assert _file(report, "src/utils.js")["total_churn"] == 64


def test_utils_hotspot(report):
    """Verify src/utils.js hotspot: 12."""
    assert _file(report, "src/utils.js")["hotspot_score"] == 12


def test_middleware_churn(report):
    """Verify src/middleware.js churn: 44."""
    assert _file(report, "src/middleware.js")["total_churn"] == 44


def test_middleware_churn_not_50(report):
    """Verify middleware.js not 50 (must apply global decay)."""
    assert _file(report, "src/middleware.js")["total_churn"] != 50


def test_middleware_hotspot(report):
    """Verify src/middleware.js hotspot: 10."""
    assert _file(report, "src/middleware.js")["hotspot_score"] == 10


def test_package_json_churn(report):
    """Verify package.json churn: 18."""
    assert _file(report, "package.json")["total_churn"] == 18


def test_package_json_hotspot(report):
    """Verify package.json hotspot: 3."""
    assert _file(report, "package.json")["hotspot_score"] == 3


def test_days_integer(report):
    """Verify all days_since_last_change are integers."""
    for f in report["files"]:
        assert isinstance(f["days_since_last_change"], int)


def test_hotspot_integer(report):
    """Verify all hotspot scores are integers."""
    for f in report["files"]:
        assert f["hotspot_score"] == int(f["hotspot_score"])


def test_recency_range(report):
    """Verify all recency weights in (0, 1]."""
    for f in report["files"]:
        assert 0 < f["recency_weight"] <= 1.0


def test_churn_sum(report):
    """Verify aggregate churn across all files."""
    total = sum(f["total_churn"] for f in report["files"])
    assert total == 1311


# ── Branches ─────────────────────────────────────────────────────────────


def test_branch_main(report):
    """Verify main depth reflects octopus rule."""
    assert report["branches"]["main"]["depth"] == 8
    assert report["branches"]["main"]["head_commit"] == "d1a5e7c3"


def test_branch_main_not_11(report):
    """Verify main depth is not 11."""
    assert report["branches"]["main"]["depth"] != 11


def test_branch_feature_auth(report):
    """Verify feature-auth depth is 5."""
    assert report["branches"]["feature-auth"]["depth"] == 5


def test_branch_feature_api(report):
    """Verify feature-api depth is 9."""
    assert report["branches"]["feature-api"]["depth"] == 9


def test_branch_experimental(report):
    """Verify orphan branch depth is 0."""
    assert report["branches"]["experimental"]["depth"] == 0


# ── Review coverage ──────────────────────────────────────────────────────


def test_review_non_merge_count(report):
    """Verify 13 non-merge commits."""
    assert report["review_coverage"]["total_non_merge"] == 13


def test_review_reviewed_count(report):
    """Verify 5 reviewed (line-start only)."""
    assert report["review_coverage"]["reviewed_count"] == 5


def test_review_not_6(report):
    """Verify not 6 (mid-line false positive)."""
    assert report["review_coverage"]["reviewed_count"] != 6


def test_review_ratio(report):
    """Verify coverage ratio 5/13."""
    assert math.isclose(
        report["review_coverage"]["coverage_ratio"],
        round(5 / 13, 6), abs_tol=FLOAT_TOL
    )


# ── Language enforcement ─────────────────────────────────────────────────


def test_main_js_exists():
    """Verify /app/src/main.js exists."""
    assert (ROOT / "src" / "main.js").is_file()


def test_main_js_is_javascript():
    """Verify main.js is JavaScript."""
    content = (ROOT / "src" / "main.js").read_text(encoding="utf-8")
    assert "require(" in content or "import " in content
    assert "#!/usr/bin/env python" not in content


def test_no_python_in_app():
    """Verify no Python scripts in solution."""
    py_files = list(ROOT.glob("*.py")) + list(ROOT.glob("src/*.py"))
    assert len(py_files) == 0


def test_input_files_intact():
    """Verify 15 commit data files exist."""
    assert len(list((DATA_DIR / "commits").glob("*.json"))) == 15
