#include "solver.h"
#include <cmath>
#include <algorithm>

static std::vector<double> mat_vec(const std::vector<std::vector<double>>& A,
                                   const std::vector<double>& x) {
    int n = (int)x.size();
    std::vector<double> y(n, 0.0);
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            y[i] += A[i][j] * x[j];
    return y;
}

static double dot(const std::vector<double>& a, const std::vector<double>& b) {
    double s = 0.0;
    for (int i = 0; i < (int)a.size(); i++) s += a[i] * b[i];
    return s;
}

static double norm(const std::vector<double>& v) {
    return std::sqrt(dot(v, v));
}

SolverResult solve_cg(const FEMSystem& sys, int max_iter, double tol) {
    int n = sys.n;
    std::vector<double> x(n, 0.0);
    auto r = sys.F;
    auto Kx = mat_vec(sys.K, x);
    for (int i = 0; i < n; i++) r[i] = sys.F[i] - Kx[i];

    std::vector<double> z(n);
    for (int i = 0; i < n; i++) {
        double diag = sys.K[i][i];
        z[i] = (std::abs(diag * diag) > 1e-15) ? r[i] / (diag * diag) : r[i];
    }

    auto p = z;
    double rz = dot(r, z);

    SolverResult result;
    result.converged = false;
    result.iterations = 0;

    for (int iter = 0; iter < max_iter; iter++) {
        auto Kp = mat_vec(sys.K, p);
        double pKp = dot(p, Kp);
        if (std::abs(pKp) < 1e-30) break;
        double alpha = rz / pKp;

        for (int i = 0; i < n; i++) {
            x[i] += alpha * p[i];
            r[i] -= alpha * Kp[i];
        }

        double r_norm = norm(r);
        result.iterations = iter + 1;
        result.final_residual = r_norm;

        if (r_norm < tol) {
            result.converged = true;
            break;
        }

        for (int i = 0; i < n; i++) {
            double diag = sys.K[i][i];
            z[i] = (std::abs(diag * diag) > 1e-15) ? r[i] / (diag * diag) : r[i];
        }

        double rz_new = dot(r, z);
        double beta = rz_new / rz;
        rz = rz_new;

        for (int i = 0; i < n; i++)
            p[i] = z[i] + beta * p[i];
    }

    result.solution = x;
    return result;
}
