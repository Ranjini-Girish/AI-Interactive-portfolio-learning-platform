#pragma once

inline double N1(double xi, double eta) { return 1.0 - xi - eta; }
inline double N2(double xi, double eta) { return xi; }
inline double N3(double xi, double eta) { return eta; }

inline double dN1_dxi()  { return -1.0; }
inline double dN1_deta() { return -1.0; }
inline double dN2_dxi()  { return  1.0; }
inline double dN2_deta() { return  0.0; }
inline double dN3_dxi()  { return  0.0; }
inline double dN3_deta() { return  1.0; }
