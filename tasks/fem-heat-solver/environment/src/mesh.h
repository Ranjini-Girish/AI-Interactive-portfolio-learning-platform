#pragma once
#include <vector>
#include <string>

struct Node {
    int id;
    double x, y;
};

struct Element {
    int id;
    int nodes[3];
};

struct BoundaryCondition {
    int node_id;
    double value;
};

struct MeshData {
    std::vector<Node> nodes;
    std::vector<Element> elements;
    std::vector<BoundaryCondition> dirichlet;
    double conductivity;
    double heat_source;
    int precision;
    std::string output_path;
};

MeshData load_mesh(const std::string& mesh_file, const std::string& config_file);
