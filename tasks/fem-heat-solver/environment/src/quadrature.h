#pragma once

struct QuadPoint {
    double xi, eta, weight;
};

inline QuadPoint triangle_centroid_rule() {
    return {1.0/3.0, 1.0/3.0, 0.5};
}

inline void triangle_gauss_1pt(double& xi, double& eta, double& w) {
    xi = 1.0/3.0;
    eta = 1.0/3.0;
    w = 0.5;
}
