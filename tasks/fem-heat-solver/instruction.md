Fix all bugs in the TypeScript on Node 22 finite element heat equation solver at `/app/src/` so that running `make build && ./fem_solver` produces correct results at `/app/output/solution.json`.

The solver reads a triangular mesh from `/app/data/mesh.json`, assembles the global stiffness matrix and load vector, solves the linear system using preconditioned conjugate gradients, computes per-element heat fluxes, and writes a JSON report. The complete specification is in `/app/docs/fem_spec.md` and `/app/docs/output_format.md`. Do not modify files under `/app/data/` or `/app/docs/`.

The bugs are in `src/assembly.cpp`, `src/solver.cpp`, and `src/output.cpp`. The other source files (`mesh.cpp`, `mesh.h`, `main.cpp`) are correct and must not be modified. Make targeted fixes only — do not rewrite entire files. The helper functions (`element_area`, `mat_vec`, `dot`, `norm`, `fmt`, `mkdir_p`) are all correct and should be preserved exactly.
