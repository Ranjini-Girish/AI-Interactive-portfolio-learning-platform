#pragma once
#include <vector>
#include <cmath>

inline double vec_norm(const std::vector<double>& v) {
    double s = 0.0;
    for (auto x : v) s += x * x;
    return std::sqrt(s);
}

inline double vec_dot(const std::vector<double>& a, const std::vector<double>& b) {
    double s = 0.0;
    for (int i = 0; i < (int)a.size(); i++) s += a[i] * b[i];
    return s;
}

inline std::vector<double> vec_sub(const std::vector<double>& a, const std::vector<double>& b) {
    std::vector<double> r(a.size());
    for (int i = 0; i < (int)a.size(); i++) r[i] = a[i] - b[i];
    return r;
}

inline std::vector<double> vec_add(const std::vector<double>& a, const std::vector<double>& b) {
    std::vector<double> r(a.size());
    for (int i = 0; i < (int)a.size(); i++) r[i] = a[i] + b[i];
    return r;
}

inline std::vector<double> vec_scale(const std::vector<double>& v, double s) {
    std::vector<double> r(v.size());
    for (int i = 0; i < (int)v.size(); i++) r[i] = v[i] * s;
    return r;
}
