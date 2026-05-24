#pragma once
#include "mesh.h"
#include "solver.h"
#include <string>

void write_solution(const std::string& path, const MeshData& mesh,
                    const SolverResult& result, int precision);
