#pragma once
#include "mesh.h"
#include <vector>

struct FEMSystem {
    int n;
    std::vector<std::vector<double>> K;
    std::vector<double> F;
};

FEMSystem assemble(const MeshData& mesh);
void apply_boundary_conditions(FEMSystem& sys, const std::vector<BoundaryCondition>& bcs);
