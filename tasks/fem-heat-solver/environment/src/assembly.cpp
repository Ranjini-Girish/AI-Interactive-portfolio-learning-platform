#include "assembly.h"
#include <cmath>

static double element_area(const Node& n1, const Node& n2, const Node& n3) {
    return 0.5 * std::abs(n1.x * (n2.y - n3.y) + n2.x * (n3.y - n1.y) + n3.x * (n1.y - n2.y));
}

FEMSystem assemble(const MeshData& mesh) {
    int n = (int)mesh.nodes.size();
    FEMSystem sys;
    sys.n = n;
    sys.K.assign(n, std::vector<double>(n, 0.0));
    sys.F.assign(n, 0.0);

    double k = mesh.conductivity;
    double Q = mesh.heat_source;

    for (const auto& elem : mesh.elements) {
        const Node& n1 = mesh.nodes[elem.nodes[0]];
        const Node& n2 = mesh.nodes[elem.nodes[1]];
        const Node& n3 = mesh.nodes[elem.nodes[2]];

        double A = element_area(n1, n2, n3);
        if (A < 1e-15) continue;

        double b[3], c[3];
        b[0] = n2.y - n3.y;
        b[1] = n3.y - n1.y;
        b[2] = n1.y - n2.y;
        c[0] = n3.x - n2.x;
        c[1] = n1.x - n3.x;
        c[2] = n2.x - n1.x;

        double coeff = k / (2.0 * A);

        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                sys.K[elem.nodes[i]][elem.nodes[j]] += coeff * (b[i] * b[j] + c[i] * c[j]);
            }
        }

        for (int i = 0; i < 3; i++) {
            sys.F[elem.nodes[i]] += A / 6.0;
        }
    }

    return sys;
}

void apply_boundary_conditions(FEMSystem& sys, const std::vector<BoundaryCondition>& bcs) {
    for (const auto& bc : bcs) {
        int i = bc.node_id;
        double val = bc.value;

        for (int j = 0; j < sys.n; j++) {
            sys.K[i][j] = 0.0;
            sys.K[j][i] = 0.0;
        }
        sys.K[i][i] = 1.0;
        sys.F[i] = val;
    }
}
