#pragma once
#include "assembly.h"
#include <vector>

struct SolverResult {
    std::vector<double> solution;
    bool converged;
    int iterations;
    double final_residual;
};

SolverResult solve_cg(const FEMSystem& sys, int max_iter, double tol);
