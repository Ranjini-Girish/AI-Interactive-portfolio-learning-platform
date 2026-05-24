#include "output.h"
#include <fstream>
#include <iomanip>
#include <cmath>
#include <sstream>
#include <algorithm>
#include <sys/stat.h>

static std::string fmt(double val, int prec) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(prec) << val;
    return oss.str();
}

static void mkdir_p(const std::string& path) {
    size_t pos = 0;
    while ((pos = path.find('/', pos + 1)) != std::string::npos) {
        ::mkdir(path.substr(0, pos).c_str(), 0755);
    }
}

void write_solution(const std::string& path, const MeshData& mesh,
                    const SolverResult& result, int precision) {
    mkdir_p(path);
    std::ofstream out(path);
    if (!out.is_open()) return;

    const auto& T = result.solution;
    int n = (int)mesh.nodes.size();
    double k = mesh.conductivity;

    out << "{\n";

    out << "  \"metadata\": {\n";
    out << "    \"solver_type\": \"conjugate_gradient\",\n";
    out << "    \"preconditioner\": \"jacobi\",\n";
    out << "    \"mesh_nodes\": " << n << ",\n";
    out << "    \"mesh_elements\": " << mesh.elements.size() << ",\n";
    out << "    \"convergence\": {\n";
    out << "      \"converged\": " << (result.converged ? "true" : "false") << ",\n";
    out << "      \"iterations\": " << result.iterations << ",\n";
    out << "      \"final_residual\": " << fmt(result.final_residual, precision) << "\n";
    out << "    }\n";
    out << "  },\n";

    out << "  \"node_temperatures\": [\n";
    for (int i = 0; i < n; i++) {
        out << "    {\"node_id\": " << mesh.nodes[i].id
            << ", \"x\": " << fmt(mesh.nodes[i].x, precision)
            << ", \"y\": " << fmt(mesh.nodes[i].y, precision)
            << ", \"temperature\": " << fmt(T[i], precision) << "}";
        if (i < n - 1) out << ",";
        out << "\n";
    }
    out << "  ],\n";

    out << "  \"element_data\": [\n";
    for (int e = 0; e < (int)mesh.elements.size(); e++) {
        const auto& elem = mesh.elements[e];
        const Node& n1 = mesh.nodes[elem.nodes[0]];
        const Node& n2 = mesh.nodes[elem.nodes[1]];
        const Node& n3 = mesh.nodes[elem.nodes[2]];
        double A = 0.5 * std::abs(n1.x*(n2.y-n3.y) + n2.x*(n3.y-n1.y) + n3.x*(n1.y-n2.y));

        double b[3] = {n2.y - n3.y, n3.y - n1.y, n1.y - n2.y};
        double c[3] = {n3.x - n2.x, n1.x - n3.x, n2.x - n1.x};

        double T1 = T[elem.nodes[0]], T2 = T[elem.nodes[1]], T3 = T[elem.nodes[2]];
        double avg_T = (T1 + T2 + T3) / 3.0;

        double qx = k * (b[0]*T1 + b[1]*T2 + b[2]*T3) / (2.0 * A);
        double qy = k * (c[0]*T1 + c[1]*T2 + c[2]*T3) / (2.0 * A);

        out << "    {\"element_id\": " << elem.id
            << ", \"nodes\": [" << elem.nodes[0] << ", " << elem.nodes[1] << ", " << elem.nodes[2] << "]"
            << ", \"avg_temperature\": " << fmt(avg_T, precision)
            << ", \"heat_flux_x\": " << fmt(qx, precision)
            << ", \"heat_flux_y\": " << fmt(qy, precision) << "}";
        if (e < (int)mesh.elements.size() - 1) out << ",";
        out << "\n";
    }
    out << "  ],\n";

    double min_T = T[0], max_T = T[0], sum_T = 0.0;
    for (int i = 0; i < n; i++) {
        if (T[i] < min_T) min_T = T[i];
        if (T[i] > max_T) max_T = T[i];
        sum_T += T[i];
    }
    double mean_T = sum_T / (n - 1);

    double total_qx = 0.0, total_qy = 0.0;
    for (int e = 0; e < (int)mesh.elements.size(); e++) {
        const auto& elem = mesh.elements[e];
        const Node& nn1 = mesh.nodes[elem.nodes[0]];
        const Node& nn2 = mesh.nodes[elem.nodes[1]];
        const Node& nn3 = mesh.nodes[elem.nodes[2]];
        double A = 0.5 * std::abs(nn1.x*(nn2.y-nn3.y) + nn2.x*(nn3.y-nn1.y) + nn3.x*(nn1.y-nn2.y));
        double bb[3] = {nn2.y - nn3.y, nn3.y - nn1.y, nn1.y - nn2.y};
        double cc[3] = {nn3.x - nn2.x, nn1.x - nn3.x, nn2.x - nn1.x};
        double TT1 = T[elem.nodes[0]], TT2 = T[elem.nodes[1]], TT3 = T[elem.nodes[2]];
        total_qx += k * (bb[0]*TT1 + bb[1]*TT2 + bb[2]*TT3) / (2.0 * A);
        total_qy += k * (cc[0]*TT1 + cc[1]*TT2 + cc[2]*TT3) / (2.0 * A);
    }

    out << "  \"summary\": {\n";
    out << "    \"min_temperature\": " << fmt(min_T, precision) << ",\n";
    out << "    \"max_temperature\": " << fmt(max_T, precision) << ",\n";
    out << "    \"total_heat_flux_x\": " << fmt(total_qx, precision) << ",\n";
    out << "    \"total_heat_flux_y\": " << fmt(total_qy, precision) << ",\n";
    out << "    \"mean_temperature\": " << fmt(mean_T, precision) << "\n";
    out << "  }\n";
    out << "}\n";
}
