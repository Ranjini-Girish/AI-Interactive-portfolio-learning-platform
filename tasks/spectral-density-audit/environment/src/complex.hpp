#ifndef COMPLEX_HPP
#define COMPLEX_HPP

struct Complex {
    double re = 0.0;
    double im = 0.0;

    Complex() = default;
    Complex(double r, double i) : re(r), im(i) {}

    Complex operator+(const Complex& o) const { return {re + o.re, im + o.im}; }
    Complex operator-(const Complex& o) const { return {re - o.re, im - o.im}; }
    Complex operator*(const Complex& o) const {
        return {re * o.re - im * o.im, re * o.im + im * o.re};
    }
    double mag_squared() const { return re * re + im * im; }
};

#endif
