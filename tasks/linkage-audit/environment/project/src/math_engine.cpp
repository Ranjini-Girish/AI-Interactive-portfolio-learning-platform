#include "math_utils.h"
#include "logger.h"

double compute(const Data& d) {
    log_message("computing value");
    return d.value * 2.0;
}

double transform(double x, double y) {
    return x * x + y * y;
}
