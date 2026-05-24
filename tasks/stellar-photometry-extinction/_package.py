"""Create flat submission zip for stellar-photometry-extinction-audit-hard."""
import os
import zipfile
from pathlib import Path

BASE = Path(__file__).parent
ZIP_NAME = "stellar-photometry-extinction-audit-hard.zip"
OUT_PATH = BASE.parent / ZIP_NAME

INCLUDE = [
    "task.toml",
    "instruction.md",
    "environment/Dockerfile",
    "environment/.dockerignore",
    "environment/app/Makefile",
    "environment/app/README.md",
    "environment/app/src/photo_audit.cpp",
    "environment/app/docs/input_format.md",
    "environment/app/docs/findings.md",
    "environment/app/docs/edge_cases.md",
    "environment/app/docs/extinction_algorithm.md",
    "environment/app/docs/output_format.md",
    "environment/app/data/manifest.json",
    "environment/app/data/exclusions.json",
    "environment/app/data/site.json",
    "environment/app/data/policy.json",
    "environment/app/data/instrument.json",
    "environment/app/data/catalog/programs.csv",
    "environment/app/data/catalog/standards.csv",
    "solution/solve.sh",
    "tests/test.sh",
    "tests/test_outputs.py",
    "tests/reference_solver.py",
]

for i in range(1, 16):
    INCLUDE.append(f"environment/app/data/observations/N{i:03d}.csv")

with zipfile.ZipFile(OUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
    for arc_name in INCLUDE:
        src = BASE / arc_name
        assert src.exists(), f"Missing: {src}"
        zf.write(src, arc_name)
        print(f"  {arc_name}")

print(f"\nCreated {OUT_PATH}")
print(f"Files: {len(INCLUDE)}")
print(f"Size: {os.path.getsize(OUT_PATH)} bytes")
