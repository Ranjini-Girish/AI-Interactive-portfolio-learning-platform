"""Tests for atmospheric-profile-analysis-hard."""
import json
import math
import pathlib

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

THERMO_TOL = 5e-3
CAPE_TOL = 15.0
INDEX_TOL = 0.5
PW_TOL = 0.5
SHEAR_TOL = 0.5
BV_TOL = 1e-4
W_TOL = 5e-5
VP_TOL = 0.05
RH_TOL = 0.5
LCL_P_TOL = 1.0
LCL_T_TOL = 0.05


def load_report():
    """Load the main analysis output JSON."""
    p = OUT_DIR / "analysis.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def profile_by(station, launch=None):
    """Find profile by station_id and optionally launch_time."""
    for p in R["profiles"]:
        if p["station_id"] == station:
            if launch is None or p["launch_time"] == launch:
                return p
    return None


# ─── Output file structure ───────────────────────────────────────────────────


def test_output_file_exists():
    """Verify the analysis output file was created."""
    assert (OUT_DIR / "analysis.json").is_file()


def test_top_level_keys():
    """Verify top-level keys are exactly metadata, profiles, summary."""
    assert set(R.keys()) == {"metadata", "profiles", "summary"}


def test_metadata_constants():
    """Verify physical constants are present and correct."""
    c = R["metadata"]["constants"]
    assert math.isclose(c["R_d"], 287.05, abs_tol=0.01)
    assert math.isclose(c["c_pd"], 1004.68, abs_tol=0.01)
    assert math.isclose(c["g"], 9.80665, abs_tol=0.0001)
    assert math.isclose(c["P_0"], 1000.0, abs_tol=0.1)
    assert math.isclose(c["R_v"], 461.52, abs_tol=0.01)
    assert "epsilon" in c


def test_sounding_count():
    """Verify the metadata reports the correct number of soundings."""
    assert R["metadata"]["sounding_count"] == 8


def test_profiles_count():
    """Verify 8 profile objects exist in the profiles array."""
    assert len(R["profiles"]) == 8


def test_profiles_sorted_by_station_then_time():
    """Verify profiles are sorted by station_id ASC then launch_time ASC."""
    keys = [(p["station_id"], p["launch_time"]) for p in R["profiles"]]
    assert keys == sorted(keys), f"Profiles not sorted: {keys}"


def test_profile_has_required_fields():
    """Verify each profile has station_id, launch_time, levels, derived."""
    for p in R["profiles"]:
        assert "station_id" in p
        assert "launch_time" in p
        assert "levels" in p
        assert "derived" in p


def test_level_has_all_keys():
    """Verify each level object has all 13 required keys."""
    required = {
        "brunt_vaisala_Hz", "e_hPa", "e_sat_hPa", "height_m",
        "mixing_ratio_kgkg", "pressure_hPa", "relative_humidity_pct",
        "temperature_K", "theta_K", "theta_v_K", "virtual_temp_K",
        "wind_direction_deg", "wind_speed_ms",
    }
    for p in R["profiles"]:
        for lev in p["levels"]:
            missing = required - set(lev.keys())
            assert not missing, f"Missing keys {missing} in {p['station_id']}"


def test_derived_has_all_keys():
    """Verify each derived object has all 9 required keys."""
    required = {
        "bulk_shear_0_6km_ms", "cape_J_per_kg", "cin_J_per_kg",
        "k_index", "lcl_pressure_hPa", "lcl_temperature_K",
        "lifted_index", "precipitable_water_mm", "total_totals",
    }
    for p in R["profiles"]:
        missing = required - set(p["derived"].keys())
        assert not missing, f"Missing derived keys {missing} in {p['station_id']}"


def test_summary_keys():
    """Verify summary has exactly the required keys."""
    required = {
        "max_cape_J_per_kg", "max_cape_station",
        "mean_precipitable_water_mm",
        "profiles_with_cape_count", "profiles_without_cape_count",
    }
    assert set(R["summary"].keys()) == required


# ─── JSON formatting ────────────────────────────────────────────────────────


def test_json_trailing_newline():
    """Verify the output file ends with exactly one trailing newline."""
    raw = (OUT_DIR / "analysis.json").read_text(encoding="utf-8")
    assert raw.endswith("\n"), "Missing trailing newline"
    assert not raw.endswith("\n\n"), "Extra trailing newlines"


def test_json_two_space_indent():
    """Verify JSON uses 2-space indentation."""
    raw = (OUT_DIR / "analysis.json").read_text(encoding="utf-8")
    lines = raw.split("\n")
    indented = [ln for ln in lines if ln.startswith("  ") and not ln.startswith("    ")]
    assert len(indented) > 0, "No 2-space indented lines found"
    four_space_only = [
        ln for ln in lines
        if ln.startswith("    ") and not ln.startswith("      ")
    ]
    assert len(four_space_only) > 0, "No 4-space (nested) lines found"


def test_json_keys_sorted_alphabetically():
    """Verify keys are sorted alphabetically within each object."""
    raw = (OUT_DIR / "analysis.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    _verify_sorted_keys(parsed, "root")


def _verify_sorted_keys(obj, path):
    if isinstance(obj, dict):
        keys = list(obj.keys())
        assert keys == sorted(keys), f"Keys not sorted at {path}: {keys}"
        for k, v in obj.items():
            _verify_sorted_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _verify_sorted_keys(item, f"{path}[{i}]")


# ─── Saturation vapor pressure (Buck 1981) — TRAP: models use Tetens ────────


def test_esat_buck_surface_alpha():
    """Verify e_sat at ALPHA surface (28°C) uses Buck equation."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    assert math.isclose(p["levels"][0]["e_sat_hPa"], 37.8139, abs_tol=VP_TOL)


def test_esat_buck_surface_bravo():
    """Verify e_sat at BRAVO surface (34°C) uses Buck equation."""
    p = profile_by("BRAVO", "2024-06-15T12:00:00Z")
    assert math.isclose(p["levels"][0]["e_sat_hPa"], 53.2287, abs_tol=VP_TOL)


def test_esat_buck_cold_level():
    """Verify e_sat at cold temperature (-52°C) at ALPHA 300 hPa."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    lev_300 = next(lev for lev in p["levels"] if lev["pressure_hPa"] == 300)
    assert math.isclose(lev_300["e_sat_hPa"], 0.0508, abs_tol=0.005)


def test_actual_vapor_pressure_from_dewpoint():
    """Verify actual vapor pressure computed from dewpoint at ALPHA sfc."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    assert math.isclose(p["levels"][0]["e_hPa"], 20.6391, abs_tol=VP_TOL)


# ─── Mixing ratio — TRAP: models use q = eps*e/P instead of w = eps*e/(P-e) ─


def test_mixing_ratio_alpha_surface():
    """Verify mixing ratio uses w=eps*e/(P-e), not specific humidity."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    w = p["levels"][0]["mixing_ratio_kgkg"]
    assert math.isclose(w, 0.012936, abs_tol=W_TOL)


def test_mixing_ratio_foxtrot_surface():
    """Verify mixing ratio at FOXTROT sfc (high moisture) uses correct formula."""
    p = profile_by("FOXTROT", "2024-06-15T12:00:00Z")
    w = p["levels"][0]["mixing_ratio_kgkg"]
    assert math.isclose(w, 0.020062, abs_tol=W_TOL)
    wrong_q = 0.62197 * 31.6853 / 1014.0
    assert abs(w - wrong_q) > 0.0003, "Appears to use specific humidity formula"


def test_mixing_ratio_bravo_surface():
    """Verify mixing ratio at BRAVO surface is correct."""
    p = profile_by("BRAVO", "2024-06-15T12:00:00Z")
    assert math.isclose(
        p["levels"][0]["mixing_ratio_kgkg"], 0.016755, abs_tol=W_TOL
    )


# ─── Virtual temperature — TRAP: models use approximation T*(1+0.608w) ──────


def test_virtual_temp_alpha_surface():
    """Verify virtual temperature uses exact formula, not linear approx."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    tv = p["levels"][0]["virtual_temp_K"]
    assert math.isclose(tv, 303.4875, abs_tol=THERMO_TOL)


def test_virtual_temp_foxtrot_surface():
    """Verify virtual temperature at FOXTROT sfc (moist, large w) is exact."""
    p = profile_by("FOXTROT", "2024-06-15T12:00:00Z")
    tv = p["levels"][0]["virtual_temp_K"]
    assert math.isclose(tv, 306.7738, abs_tol=THERMO_TOL)


# ─── Potential temperature ──────────────────────────────────────────────────


def test_theta_at_reference_pressure():
    """Verify theta ≈ T when P ≈ P_0 (ALPHA sfc at 1013 hPa)."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    theta = p["levels"][0]["theta_K"]
    assert math.isclose(theta, 300.0407, abs_tol=THERMO_TOL)


def test_theta_increases_aloft():
    """Verify potential temperature generally increases with height."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    thetas = [lev["theta_K"] for lev in p["levels"]]
    top_half = thetas[len(thetas) // 2:]
    assert top_half == sorted(top_half), "Theta not increasing in upper levels"


def test_theta_v_larger_than_theta():
    """Verify theta_v >= theta at moist levels (moisture adds buoyancy)."""
    p = profile_by("FOXTROT", "2024-06-15T12:00:00Z")
    for lev in p["levels"][:6]:
        assert lev["theta_v_K"] >= lev["theta_K"] - 0.01, (
            f"theta_v < theta at {lev['pressure_hPa']} hPa"
        )


# ─── Relative humidity ──────────────────────────────────────────────────────


def test_rh_range():
    """Verify relative humidity is between 0 and 100 for all levels."""
    for p in R["profiles"]:
        for lev in p["levels"]:
            assert 0 <= lev["relative_humidity_pct"] <= 100, (
                f"RH out of range at {p['station_id']} {lev['pressure_hPa']}"
            )


def test_rh_alpha_surface():
    """Verify relative humidity at ALPHA surface is correct."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    assert math.isclose(p["levels"][0]["relative_humidity_pct"], 54.58, abs_tol=RH_TOL)


def test_rh_delta_surface_high():
    """Verify high RH at DELTA surface (small dewpoint depression)."""
    p = profile_by("DELTA", "2024-06-15T12:00:00Z")
    assert math.isclose(p["levels"][0]["relative_humidity_pct"], 82.12, abs_tol=RH_TOL)


# ─── Brunt-Väisälä — TRAP: signed N, not N²; centered finite differences ───


def test_bv_positive_stable_layer():
    """Verify positive N in a statically stable layer (DELTA surface)."""
    p = profile_by("DELTA", "2024-06-15T12:00:00Z")
    n = p["levels"][0]["brunt_vaisala_Hz"]
    assert n > 0, f"Expected positive N for stable layer, got {n}"
    assert math.isclose(n, 0.015091, abs_tol=BV_TOL)


def test_bv_negative_unstable_layer():
    """Verify negative N in unstable layer (BRAVO surface, superadiabatic)."""
    p = profile_by("BRAVO", "2024-06-15T12:00:00Z")
    n = p["levels"][0]["brunt_vaisala_Hz"]
    assert n < 0, f"Expected negative N for unstable layer, got {n}"
    assert math.isclose(n, -0.004431, abs_tol=BV_TOL)


def test_bv_not_nsquared():
    """Verify output is N (Hz), not N² (s⁻²) — values should be O(0.01)."""
    for p in R["profiles"]:
        for lev in p["levels"]:
            n = lev["brunt_vaisala_Hz"]
            if n is not None:
                assert abs(n) < 0.1, (
                    f"N={n} too large; likely N² instead of N at "
                    f"{p['station_id']} {lev['pressure_hPa']}"
                )


def test_bv_centered_differences():
    """Verify centered differences are used for interior levels."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    n_interior = p["levels"][1]["brunt_vaisala_Hz"]
    assert math.isclose(n_interior, -0.006848, abs_tol=BV_TOL)


# ─── LCL (Bolton 1980) — TRAP: models use Espy or simpler approximation ────


def test_lcl_temperature_alpha():
    """Verify LCL temperature from Bolton formula for ALPHA 12Z."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    assert math.isclose(
        p["derived"]["lcl_temperature_K"], 288.8388, abs_tol=LCL_T_TOL
    )


def test_lcl_pressure_alpha():
    """Verify LCL pressure from Poisson relation for ALPHA 12Z."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    assert math.isclose(
        p["derived"]["lcl_pressure_hPa"], 875.31, abs_tol=LCL_P_TOL
    )


def test_lcl_temperature_foxtrot():
    """Verify LCL temperature for FOXTROT 12Z (small dewpoint depression)."""
    p = profile_by("FOXTROT", "2024-06-15T12:00:00Z")
    assert math.isclose(
        p["derived"]["lcl_temperature_K"], 296.9371, abs_tol=LCL_T_TOL
    )


def test_lcl_pressure_delta():
    """Verify LCL pressure for stable DELTA (near surface)."""
    p = profile_by("DELTA", "2024-06-15T12:00:00Z")
    assert math.isclose(
        p["derived"]["lcl_pressure_hPa"], 973.05, abs_tol=LCL_P_TOL
    )


# ─── CAPE/CIN — TRAP: must use virtual temp, trapezoidal integration ────────


def test_cape_alpha_12z():
    """Verify CAPE for ALPHA 12Z (moderate instability) with virtual temp."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    assert math.isclose(p["derived"]["cape_J_per_kg"], 5731.13, abs_tol=CAPE_TOL)


def test_cape_bravo():
    """Verify CAPE for BRAVO (extreme instability)."""
    p = profile_by("BRAVO", "2024-06-15T12:00:00Z")
    assert math.isclose(p["derived"]["cape_J_per_kg"], 7670.31, abs_tol=CAPE_TOL)


def test_cape_zero_for_stable():
    """Verify CAPE is exactly zero for the stable DELTA profile."""
    p = profile_by("DELTA", "2024-06-15T12:00:00Z")
    assert p["derived"]["cape_J_per_kg"] == 0.0


def test_cin_large_for_stable():
    """Verify large negative CIN for the stable DELTA profile."""
    p = profile_by("DELTA", "2024-06-15T12:00:00Z")
    cin = p["derived"]["cin_J_per_kg"]
    assert cin < -1000, f"CIN for stable DELTA should be large negative, got {cin}"
    assert math.isclose(cin, -5177.42, abs_tol=50.0)


def test_cin_zero_for_uncapped():
    """Verify CIN = 0 for uncapped BRAVO profile."""
    p = profile_by("BRAVO", "2024-06-15T12:00:00Z")
    assert p["derived"]["cin_J_per_kg"] == 0.0


def test_cin_negative_or_zero():
    """Verify CIN is always <= 0 for all profiles."""
    for p in R["profiles"]:
        assert p["derived"]["cin_J_per_kg"] <= 0, (
            f"CIN positive for {p['station_id']}: {p['derived']['cin_J_per_kg']}"
        )


def test_cape_nonnegative():
    """Verify CAPE is always >= 0 for all profiles."""
    for p in R["profiles"]:
        assert p["derived"]["cape_J_per_kg"] >= 0, (
            f"CAPE negative for {p['station_id']}: {p['derived']['cape_J_per_kg']}"
        )


def test_cape_foxtrot_12z():
    """Verify CAPE for FOXTROT 12Z (tropical, highest CAPE)."""
    p = profile_by("FOXTROT", "2024-06-15T12:00:00Z")
    assert math.isclose(p["derived"]["cape_J_per_kg"], 8685.25, abs_tol=CAPE_TOL)


# ─── Precipitable water — TRAP: correct PW formula with mixing ratio ────────


def test_pw_alpha_12z():
    """Verify precipitable water for ALPHA 12Z."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    assert math.isclose(p["derived"]["precipitable_water_mm"], 23.68, abs_tol=PW_TOL)


def test_pw_foxtrot_12z():
    """Verify PW for FOXTROT 12Z (tropical, highest moisture)."""
    p = profile_by("FOXTROT", "2024-06-15T12:00:00Z")
    assert math.isclose(p["derived"]["precipitable_water_mm"], 38.31, abs_tol=PW_TOL)


def test_pw_delta():
    """Verify PW for DELTA (marine, moderate moisture)."""
    p = profile_by("DELTA", "2024-06-15T12:00:00Z")
    assert math.isclose(p["derived"]["precipitable_water_mm"], 16.26, abs_tol=PW_TOL)


def test_pw_physically_reasonable():
    """Verify PW is between 5 and 80 mm for all profiles (physical bounds)."""
    for p in R["profiles"]:
        pw = p["derived"]["precipitable_water_mm"]
        assert 5.0 < pw < 80.0, (
            f"PW {pw} mm out of physical range for {p['station_id']}"
        )


# ─── Stability indices — TRAP: log-linear interpolation, not linear ─────────


def test_k_index_alpha_12z():
    """Verify K-Index for ALPHA 12Z using log-linear interpolation."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    assert math.isclose(p["derived"]["k_index"], 26.0, abs_tol=INDEX_TOL)


def test_total_totals_bravo():
    """Verify Total Totals index for BRAVO."""
    p = profile_by("BRAVO", "2024-06-15T12:00:00Z")
    assert math.isclose(p["derived"]["total_totals"], 64.0, abs_tol=INDEX_TOL)


def test_lifted_index_alpha_12z():
    """Verify Lifted Index for ALPHA 12Z (negative = unstable)."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    assert math.isclose(p["derived"]["lifted_index"], -16.36, abs_tol=INDEX_TOL)


def test_lifted_index_delta_positive():
    """Verify Lifted Index for DELTA is positive (stable)."""
    p = profile_by("DELTA", "2024-06-15T12:00:00Z")
    assert p["derived"]["lifted_index"] > 0, "LI should be positive for stable"
    assert math.isclose(p["derived"]["lifted_index"], 9.3, abs_tol=INDEX_TOL)


def test_indices_null_for_elevated_station():
    """Verify K-Index and TT are null for CHARLIE (surface above 850 hPa)."""
    p = profile_by("CHARLIE", "2024-06-15T12:00:00Z")
    assert p["derived"]["k_index"] is None, "K-Index should be null for CHARLIE"
    assert p["derived"]["total_totals"] is None, "TT should be null for CHARLIE"


def test_lifted_index_exists_for_charlie():
    """Verify Lifted Index is computed for CHARLIE (500 hPa exists)."""
    p = profile_by("CHARLIE", "2024-06-15T12:00:00Z")
    assert p["derived"]["lifted_index"] is not None
    assert math.isclose(p["derived"]["lifted_index"], -10.82, abs_tol=INDEX_TOL)


# ─── Bulk wind shear ────────────────────────────────────────────────────────


def test_shear_alpha_12z():
    """Verify 0-6 km bulk wind shear for ALPHA 12Z."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    assert math.isclose(
        p["derived"]["bulk_shear_0_6km_ms"], 32.0, abs_tol=SHEAR_TOL
    )


def test_shear_bravo():
    """Verify bulk shear for BRAVO (strong shear environment)."""
    p = profile_by("BRAVO", "2024-06-15T12:00:00Z")
    assert math.isclose(
        p["derived"]["bulk_shear_0_6km_ms"], 39.98, abs_tol=SHEAR_TOL
    )


def test_shear_positive():
    """Verify shear magnitudes are non-negative for all profiles."""
    for p in R["profiles"]:
        s = p["derived"]["bulk_shear_0_6km_ms"]
        if s is not None:
            assert s >= 0, f"Negative shear for {p['station_id']}: {s}"


# ─── Summary section ────────────────────────────────────────────────────────


def test_summary_max_cape():
    """Verify max CAPE value in summary."""
    assert math.isclose(R["summary"]["max_cape_J_per_kg"], 8685.25, abs_tol=CAPE_TOL)


def test_summary_max_cape_station():
    """Verify the station with maximum CAPE is FOXTROT."""
    assert R["summary"]["max_cape_station"] == "FOXTROT"


def test_summary_mean_pw():
    """Verify mean precipitable water across all profiles."""
    assert math.isclose(
        R["summary"]["mean_precipitable_water_mm"], 25.45, abs_tol=PW_TOL
    )


def test_summary_cape_counts():
    """Verify counts of profiles with and without CAPE."""
    assert R["summary"]["profiles_with_cape_count"] == 7
    assert R["summary"]["profiles_without_cape_count"] == 1


def test_summary_cape_counts_sum():
    """Verify CAPE counts sum to total profile count."""
    total = (
        R["summary"]["profiles_with_cape_count"]
        + R["summary"]["profiles_without_cape_count"]
    )
    assert total == len(R["profiles"])


# ─── Cross-field consistency checks ─────────────────────────────────────────


def test_virtual_temp_greater_than_temp():
    """Verify T_v >= T at moist levels where w > 0."""
    for p in R["profiles"]:
        for lev in p["levels"]:
            if lev["mixing_ratio_kgkg"] > 0.001:
                assert lev["virtual_temp_K"] >= lev["temperature_K"] - 0.01, (
                    f"Tv < T at {p['station_id']} {lev['pressure_hPa']}"
                )


def test_esat_exceeds_e():
    """Verify saturation vapor pressure >= actual vapor pressure."""
    for p in R["profiles"]:
        for lev in p["levels"]:
            assert lev["e_sat_hPa"] >= lev["e_hPa"] - 0.01, (
                f"e > e_sat at {p['station_id']} {lev['pressure_hPa']}"
            )


def test_levels_sorted_by_pressure_desc():
    """Verify levels within each profile are sorted by descending pressure."""
    for p in R["profiles"]:
        pressures = [lev["pressure_hPa"] for lev in p["levels"]]
        assert pressures == sorted(pressures, reverse=True), (
            f"Levels not sorted by descending pressure in {p['station_id']}"
        )


def test_height_increases_with_decreasing_pressure():
    """Verify height increases as pressure decreases."""
    for p in R["profiles"]:
        heights = [lev["height_m"] for lev in p["levels"]]
        assert heights == sorted(heights), (
            f"Heights not increasing in {p['station_id']}"
        )


def test_temperature_K_conversion():
    """Verify temperatures are in Kelvin (above 200 K for all levels)."""
    for p in R["profiles"]:
        for lev in p["levels"]:
            assert lev["temperature_K"] > 190, (
                f"Implausible T={lev['temperature_K']} at {p['station_id']}"
            )


def test_mixing_ratio_decreases_aloft():
    """Verify mixing ratio generally decreases with height."""
    p = profile_by("ALPHA", "2024-06-15T12:00:00Z")
    w_sfc = p["levels"][0]["mixing_ratio_kgkg"]
    w_top = p["levels"][-1]["mixing_ratio_kgkg"]
    assert w_top < w_sfc * 0.01, "Mixing ratio should drop by >100x from sfc to top"


def test_cape_consistent_with_lifted_index():
    """Verify LI sign is consistent with CAPE: negative LI implies CAPE > 0."""
    for p in R["profiles"]:
        li = p["derived"]["lifted_index"]
        cape = p["derived"]["cape_J_per_kg"]
        if li is not None and li < -2:
            assert cape > 0, (
                f"LI={li} but CAPE=0 for {p['station_id']}"
            )


def test_alpha_two_soundings():
    """Verify ALPHA has two soundings at different times."""
    alpha = [p for p in R["profiles"] if p["station_id"] == "ALPHA"]
    assert len(alpha) == 2
    times = [p["launch_time"] for p in alpha]
    assert "2024-06-15T12:00:00Z" in times
    assert "2024-06-16T00:00:00Z" in times


def test_foxtrot_two_soundings():
    """Verify FOXTROT has two soundings at different times."""
    fox = [p for p in R["profiles"] if p["station_id"] == "FOXTROT"]
    assert len(fox) == 2


def test_all_six_stations_present():
    """Verify all six stations appear in the profiles."""
    stations = {p["station_id"] for p in R["profiles"]}
    expected = {"ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT"}
    assert stations == expected
