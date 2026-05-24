#include "mesh.h"
#include "assembly.h"
#include "solver.h"
#include "output.h"
#include <iostream>
#include <cstdlib>

int main() {
    try {
        MeshData mesh = load_mesh("/app/data/mesh.json", "/app/data/config.json");

        FEMSystem sys = assemble(mesh);
        apply_boundary_conditions(sys, mesh.dirichlet);

        SolverResult result = solve_cg(sys, 1000, 1e-10);

        if (!result.converged) {
            std::cerr << "Warning: solver did not converge after "
                      << result.iterations << " iterations" << std::endl;
        }

        write_solution(mesh.output_path, mesh, result, mesh.precision);
        std::cout << "Solution written to " << mesh.output_path << std::endl;
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "Error: " << ex.what() << std::endl;
        return 1;
    }
}
