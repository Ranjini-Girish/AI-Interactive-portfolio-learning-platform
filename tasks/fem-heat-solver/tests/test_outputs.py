"""Tests for cpp-fem-heat-solver-hard."""
import json
import math
import pathlib
import hashlib

ROOT = pathlib.Path("/app")
OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')
FLOAT_TOL = 5e-4


def load_report():
    p = OUT_DIR / "solution.json"
    assert p.is_file(), f"Missing output: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()
NODES = {n["node_id"]: n for n in R["node_temperatures"]}
ELEMS = {e["element_id"]: e for e in R["element_data"]}


def test_output_exists():
    assert (OUT_DIR / "solution.json").is_file()

def test_trailing_newline():
    raw = (OUT_DIR / "solution.json").read_text(encoding="utf-8")
    assert raw.endswith("}\n")

def test_top_level_keys():
    assert set(R.keys()) == {"metadata", "node_temperatures", "element_data", "summary"}

def test_top_level_key_order():
    keys = list(R.keys())
    assert keys == ["metadata", "node_temperatures", "element_data", "summary"]

def test_metadata_solver_type():
    assert R["metadata"]["solver_type"] == "conjugate_gradient"

def test_metadata_preconditioner():
    assert R["metadata"]["preconditioner"] == "jacobi"

def test_metadata_mesh_nodes():
    assert R["metadata"]["mesh_nodes"] == 36

def test_metadata_mesh_elements():
    assert R["metadata"]["mesh_elements"] == 50

def test_convergence_converged():
    assert R["metadata"]["convergence"]["converged"] is True

def test_node_count():
    assert len(R["node_temperatures"]) == 36

def test_element_count():
    assert len(R["element_data"]) == 50

def test_left_boundary_temperature():
    """Left edge nodes should have T=100."""
    assert math.isclose(NODES[0]["temperature"], 100.0, abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[6]["temperature"], 100.0, abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[12]["temperature"], 100.0, abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[18]["temperature"], 100.0, abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[24]["temperature"], 100.0, abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[30]["temperature"], 100.0, abs_tol=FLOAT_TOL)

def test_right_boundary_temperature():
    """Right edge nodes should have T=0."""
    assert math.isclose(NODES[5]["temperature"], 0.0, abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[11]["temperature"], 0.0, abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[17]["temperature"], 0.0, abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[23]["temperature"], 0.0, abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[29]["temperature"], 0.0, abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[35]["temperature"], 0.0, abs_tol=FLOAT_TOL)

def test_interior_temperatures_positive():
    """Interior nodes should have temperatures between 0 and max boundary + source contribution."""
    assert NODES[1]["temperature"] > 0.0
    assert NODES[2]["temperature"] > 0.0
    assert NODES[3]["temperature"] > 0.0
    assert NODES[4]["temperature"] > 0.0
    assert NODES[7]["temperature"] > 0.0
    assert NODES[8]["temperature"] > 0.0
    assert NODES[9]["temperature"] > 0.0
    assert NODES[10]["temperature"] > 0.0
    assert NODES[13]["temperature"] > 0.0
    assert NODES[14]["temperature"] > 0.0

def test_node_7_temperature():
    assert math.isclose(NODES[7]["temperature"], 80.533333, abs_tol=FLOAT_TOL)

def test_node_8_temperature():
    assert math.isclose(NODES[8]["temperature"], 60.8, abs_tol=FLOAT_TOL)

def test_node_9_temperature():
    assert math.isclose(NODES[9]["temperature"], 40.8, abs_tol=FLOAT_TOL)

def test_node_13_temperature():
    assert math.isclose(NODES[13]["temperature"], 80.533333, abs_tol=FLOAT_TOL)

def test_node_14_temperature():
    assert math.isclose(NODES[14]["temperature"], 60.8, abs_tol=FLOAT_TOL)

def test_node_15_temperature():
    assert math.isclose(NODES[15]["temperature"], 40.8, abs_tol=FLOAT_TOL)

def test_node_19_temperature():
    assert math.isclose(NODES[19]["temperature"], 80.533333, abs_tol=FLOAT_TOL)

def test_node_20_temperature():
    assert math.isclose(NODES[20]["temperature"], 60.8, abs_tol=FLOAT_TOL)

def test_node_21_temperature():
    assert math.isclose(NODES[21]["temperature"], 40.8, abs_tol=FLOAT_TOL)

def test_node_25_temperature():
    assert math.isclose(NODES[25]["temperature"], 80.533333, abs_tol=FLOAT_TOL)

def test_node_26_temperature():
    assert math.isclose(NODES[26]["temperature"], 60.8, abs_tol=FLOAT_TOL)

def test_node_27_temperature():
    assert math.isclose(NODES[27]["temperature"], 40.8, abs_tol=FLOAT_TOL)

def test_temperature_decreases_left_to_right():
    """Temperature should generally decrease from left to right."""
    for row in range(6):
        for col in range(6 - 1):
            n1 = NODES[row * 6 + col]["temperature"]
            n2 = NODES[row * 6 + col + 1]["temperature"]
            assert n1 >= n2 - FLOAT_TOL, f'Row {row}: T[{col}]={n1} < T[{col+1}]={n2}'

def test_element_nodes_valid():
    for e in R["element_data"]:
        assert len(e["nodes"]) == 3
        for nid in e["nodes"]:
            assert 0 <= nid < 36

def test_element_avg_temperature():
    """Average temperature should be mean of 3 node temps."""
    for e in R["element_data"]:
        t1 = NODES[e["nodes"][0]]["temperature"]
        t2 = NODES[e["nodes"][1]]["temperature"]
        t3 = NODES[e["nodes"][2]]["temperature"]
        expected = (t1 + t2 + t3) / 3.0
        assert math.isclose(e["avg_temperature"], expected, abs_tol=FLOAT_TOL)

def test_heat_flux_x_sign():
    """Heat flux q=-k*grad(T) flows from hot to cold; with T decreasing in +x, qx should be positive."""
    positive_count = sum(1 for e in R["element_data"] if e["heat_flux_x"] > 0)
    assert positive_count >= 25, "Most heat flux x should be positive (heat flows left to right)"

def test_element_0_heat_flux_x():
    assert math.isclose(ELEMS[0]["heat_flux_x"], 146.0, abs_tol=FLOAT_TOL)

def test_element_0_heat_flux_y():
    assert math.isclose(ELEMS[0]["heat_flux_y"], -0.0, abs_tol=FLOAT_TOL)

def test_element_1_heat_flux_x():
    assert math.isclose(ELEMS[1]["heat_flux_x"], 146.0, abs_tol=FLOAT_TOL)

def test_element_1_heat_flux_y():
    assert math.isclose(ELEMS[1]["heat_flux_y"], -0.0, abs_tol=FLOAT_TOL)

def test_element_10_heat_flux_x():
    assert math.isclose(ELEMS[10]["heat_flux_x"], 146.0, abs_tol=FLOAT_TOL)

def test_element_10_heat_flux_y():
    assert math.isclose(ELEMS[10]["heat_flux_y"], -0.0, abs_tol=FLOAT_TOL)

def test_element_11_heat_flux_x():
    assert math.isclose(ELEMS[11]["heat_flux_x"], 146.0, abs_tol=FLOAT_TOL)

def test_element_11_heat_flux_y():
    assert math.isclose(ELEMS[11]["heat_flux_y"], 0.0, abs_tol=FLOAT_TOL)

def test_element_24_heat_flux_x():
    assert math.isclose(ELEMS[24]["heat_flux_x"], 150.0, abs_tol=FLOAT_TOL)

def test_element_24_heat_flux_y():
    assert math.isclose(ELEMS[24]["heat_flux_y"], 0.0, abs_tol=FLOAT_TOL)

def test_element_25_heat_flux_x():
    assert math.isclose(ELEMS[25]["heat_flux_x"], 150.0, abs_tol=FLOAT_TOL)

def test_element_25_heat_flux_y():
    assert math.isclose(ELEMS[25]["heat_flux_y"], -0.0, abs_tol=FLOAT_TOL)

def test_element_48_heat_flux_x():
    assert math.isclose(ELEMS[48]["heat_flux_x"], 154.0, abs_tol=FLOAT_TOL)

def test_element_48_heat_flux_y():
    assert math.isclose(ELEMS[48]["heat_flux_y"], -0.0, abs_tol=FLOAT_TOL)

def test_element_49_heat_flux_x():
    assert math.isclose(ELEMS[49]["heat_flux_x"], 154.0, abs_tol=FLOAT_TOL)

def test_element_49_heat_flux_y():
    assert math.isclose(ELEMS[49]["heat_flux_y"], -0.0, abs_tol=FLOAT_TOL)

def test_summary_min_temperature():
    assert math.isclose(R["summary"]["min_temperature"], 0.0, abs_tol=FLOAT_TOL)

def test_summary_max_temperature():
    assert math.isclose(R["summary"]["max_temperature"], 100.0, abs_tol=FLOAT_TOL)

def test_summary_mean_temperature():
    assert math.isclose(R["summary"]["mean_temperature"], 50.444444, abs_tol=FLOAT_TOL)

def test_summary_total_heat_flux_x():
    assert math.isclose(R["summary"]["total_heat_flux_x"], 7500.0, abs_tol=0.5)

def test_summary_total_heat_flux_y():
    assert math.isclose(R["summary"]["total_heat_flux_y"], 0.0, abs_tol=0.5)

def test_summary_key_order():
    keys = list(R["summary"].keys())
    assert keys == ["min_temperature", "max_temperature", "mean_temperature", "total_heat_flux_x", "total_heat_flux_y"]

def test_binary_exists():
    assert pathlib.pathlib.pathlib.Path("/app/fem_solver").is_file(), "Binary must exist at /app/fem_solver"

def test_no_python_solution_files():
    """Solution must be C++, not Python."""
    import glob
    py_files = glob.glob("/app/*.py") + glob.glob("/app/src/*.py")
    assert len(py_files) == 0, f'Found Python files: {py_files}'

def test_source_files_exist():
    for f in ["src/main.cpp", "src/mesh.cpp", "src/assembly.cpp", "src/solver.cpp", "src/output.cpp"]:
        assert (pathlib.Path("/app") / f).is_file(), f"Missing: {f}"

def test_input_not_modified():
    mesh = (DATA_DIR / "mesh.json").read_bytes()
    assert hashlib.sha256(mesh).hexdigest() == "9bfb79c428f1059de48a1bd68530d1818fd2269e87766b3b89046a8089144e60"

def test_mesh_cpp_not_modified():
    """mesh.cpp contains correct parsing logic and must not be rewritten."""
    content = (ROOT / "src" / "mesh.cpp").read_bytes()
    h = hashlib.sha256(content).hexdigest()
    assert h == "4532137df0f1ca65888a5c4a63669dfd5e6c066193f99809cf6a6c39337973ad", \
        "mesh.cpp was modified (hash mismatch). Only assembly.cpp, solver.cpp, output.cpp need fixes."

def test_mesh_h_not_modified():
    """mesh.h defines correct data structures and must not be rewritten."""
    content = (ROOT / "src" / "mesh.h").read_bytes()
    h = hashlib.sha256(content).hexdigest()
    assert h == "b0ac5491cb640758438781d2b1a8f12e40b3e7e1a9e85b91ab29e7dc19841c8a", \
        "mesh.h was modified. Only fix bugs in assembly.cpp, solver.cpp, output.cpp."

def test_main_cpp_not_modified():
    """main.cpp orchestrates the pipeline correctly and must not be rewritten."""
    content = (ROOT / "src" / "main.cpp").read_bytes()
    h = hashlib.sha256(content).hexdigest()
    assert h == "5264968459aa5f482fcbb4b640634621ac1bea318ff592cab11d73a165a2b857", \
        "main.cpp was modified. Only fix bugs in assembly.cpp, solver.cpp, output.cpp."

def _extract_func(filepath, signature):
    """Extract a function body from start-of-line signature to next start-of-line closing brace."""
    import re
    content = pathlib.Path(filepath).read_text(encoding="utf-8")
    content = content.replace("\r\n", "\n")
    pattern = re.escape(signature)
    m = re.search(pattern, content)
    if not m:
        return None
    start = m.start()
    depth = 0
    i = content.index("{", start)
    depth = 1
    i += 1
    while i < len(content) and depth > 0:
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
        i += 1
    return content[start:i]

def test_element_area_not_modified():
    """element_area is correct and must not be rewritten."""
    body = _extract_func("/app/src/assembly.cpp", "static double element_area")
    assert body is not None, "element_area function not found"
    h = hashlib.sha256(body.encode()).hexdigest()
    assert h == "a20906013b8fff781fa5313f69bc349706f35a13f45c0ad752823001bdb488af", \
        "element_area was modified but is correct. Do not rewrite correct functions."

def test_mat_vec_not_modified():
    """mat_vec is correct and must not be rewritten."""
    body = _extract_func("/app/src/solver.cpp", "static std::vector<double> mat_vec")
    assert body is not None, "mat_vec function not found"
    h = hashlib.sha256(body.encode()).hexdigest()
    assert h == "77700ff55e9afadaa5a570b3633dce39a59dc5fce96d44fc93ecee7a7164627b", \
        "mat_vec was modified but is correct. Do not rewrite correct functions."

def test_dot_not_modified():
    """dot is correct and must not be rewritten."""
    body = _extract_func("/app/src/solver.cpp", "static double dot")
    assert body is not None, "dot function not found"
    h = hashlib.sha256(body.encode()).hexdigest()
    assert h == "f1aa01490b11d11a0c4e51baf34807de15d3c2e5b53d2e9882717223ad293a8c", \
        "dot was modified but is correct. Do not rewrite correct functions."

def test_norm_not_modified():
    """norm is correct and must not be rewritten."""
    body = _extract_func("/app/src/solver.cpp", "static double norm")
    assert body is not None, "norm function not found"
    h = hashlib.sha256(body.encode()).hexdigest()
    assert h == "18858e0e82cb7ea3c77ba725176383c4e0d74741246dde8771b527ba5c0aaff8", \
        "norm was modified but is correct. Do not rewrite correct functions."

def test_fmt_not_modified():
    """fmt helper is correct and must not be rewritten."""
    body = _extract_func("/app/src/output.cpp", "static std::string fmt")
    assert body is not None, "fmt function not found"
    h = hashlib.sha256(body.encode()).hexdigest()
    assert h == "fc9b2741dcf860e2922aa02f598f4b0bf2b07d41b90cf474d4880a751e547811", \
        "fmt was modified but is correct. Do not rewrite correct functions."

def test_mkdir_p_not_modified():
    """mkdir_p helper is correct and must not be rewritten."""
    body = _extract_func("/app/src/output.cpp", "static void mkdir_p")
    assert body is not None, "mkdir_p function not found"
    h = hashlib.sha256(body.encode()).hexdigest()
    assert h == "367817692db740fb330c1ff4e7c2f28351b94b76ab6a3ed64c26c8cd7e8da8b1", \
        "mkdir_p was modified but is correct. Do not rewrite correct functions."

def test_assembly_build_tag():
    """Build-time marker must be preserved (file must not be overwritten)."""
    content = (ROOT / "src" / "assembly.cpp").read_text(encoding="utf-8")
    assert "build-tag: fem-7a3f9e2d1b4c" in content, \
        "assembly.cpp was overwritten. Use targeted sed/awk edits, do not rewrite the file."

def test_solver_build_tag():
    """Build-time marker must be preserved (file must not be overwritten)."""
    content = (ROOT / "src" / "solver.cpp").read_text(encoding="utf-8")
    assert "build-tag: fem-8b4e1f3c2d5a" in content, \
        "solver.cpp was overwritten. Use targeted sed/awk edits, do not rewrite the file."

def test_output_build_tag():
    """Build-time marker must be preserved (file must not be overwritten)."""
    content = (ROOT / "src" / "output.cpp").read_text(encoding="utf-8")
    assert "build-tag: fem-9c5d2e4f3a6b" in content, \
        "output.cpp was overwritten. Use targeted sed/awk edits, do not rewrite the file."

def test_assembly_cpp_line_count():
    """assembly.cpp should have targeted fixes, not wholesale rewrite."""
    lines = (ROOT / "src" / "assembly.cpp").read_text(encoding="utf-8").splitlines()
    assert 59 <= len(lines) <= 73, f"assembly.cpp has {len(lines)} lines (expected 59-73)"

def test_solver_cpp_line_count():
    """solver.cpp should have targeted fixes, not wholesale rewrite."""
    lines = (ROOT / "src" / "solver.cpp").read_text(encoding="utf-8").splitlines()
    assert 77 <= len(lines) <= 87, f"solver.cpp has {len(lines)} lines (expected 77-87)"

def test_output_cpp_line_count():
    """output.cpp should have targeted fixes, not wholesale rewrite."""
    lines = (ROOT / "src" / "output.cpp").read_text(encoding="utf-8").splitlines()
    assert 111 <= len(lines) <= 121, f"output.cpp has {len(lines)} lines (expected 111-121)"

def test_convergence_iterations_reasonable():
    """Correct solution should converge quickly (< 50 iterations)."""
    iters = R["metadata"]["convergence"]["iterations"]
    assert 1 <= iters <= 50, f"Solver took {iters} iterations (expected < 50 for correct assembly)"

def test_node_temperatures_sorted():
    """node_temperatures must be sorted by node_id."""
    ids = [n["node_id"] for n in R["node_temperatures"]]
    assert ids == sorted(ids), "node_temperatures must be sorted by node_id"

def test_element_data_sorted():
    """element_data must be sorted by element_id."""
    ids = [e["element_id"] for e in R["element_data"]]
    assert ids == sorted(ids), "element_data must be sorted by element_id"

def test_symmetry_row_1_3():
    """Interior temperatures should be symmetric across rows (uniform mesh)."""
    assert math.isclose(NODES[7]["temperature"], NODES[13]["temperature"], abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[13]["temperature"], NODES[19]["temperature"], abs_tol=FLOAT_TOL)
    assert math.isclose(NODES[19]["temperature"], NODES[25]["temperature"], abs_tol=FLOAT_TOL)

def test_node_1_temperature():
    assert math.isclose(NODES[1]["temperature"], 80.533333, abs_tol=FLOAT_TOL)

def test_node_2_temperature():
    assert math.isclose(NODES[2]["temperature"], 60.8, abs_tol=FLOAT_TOL)

def test_node_3_temperature():
    assert math.isclose(NODES[3]["temperature"], 40.8, abs_tol=FLOAT_TOL)

def test_node_4_temperature():
    assert math.isclose(NODES[4]["temperature"], 20.533333, abs_tol=FLOAT_TOL)

def test_node_10_temperature():
    assert math.isclose(NODES[10]["temperature"], 20.533333, abs_tol=FLOAT_TOL)

def test_node_16_temperature():
    assert math.isclose(NODES[16]["temperature"], 20.533333, abs_tol=FLOAT_TOL)

def test_node_22_temperature():
    assert math.isclose(NODES[22]["temperature"], 20.533333, abs_tol=FLOAT_TOL)

def test_node_28_temperature():
    assert math.isclose(NODES[28]["temperature"], 20.533333, abs_tol=FLOAT_TOL)

def test_all_temperatures_in_range():
    """All temperatures should be within physical bounds."""
    for n in R["node_temperatures"]:
        assert -1.0 <= n["temperature"] <= 200.0, \
            f"Node {n['node_id']} has unreasonable temperature {n['temperature']}"

def test_element_20_heat_flux():
    assert math.isclose(ELEMS[20]["heat_flux_x"], 146.0, abs_tol=FLOAT_TOL)
    assert math.isclose(ELEMS[20]["heat_flux_y"], 0.0, abs_tol=0.01)

def test_element_30_heat_flux():
    assert math.isclose(ELEMS[30]["heat_flux_x"], 146.0, abs_tol=FLOAT_TOL)
    assert math.isclose(ELEMS[30]["heat_flux_y"], 0.0, abs_tol=0.01)

