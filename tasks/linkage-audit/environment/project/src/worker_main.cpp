#include "network.h"
#include "cache.h"
#include "math_utils.h"

int main() {
    Data d = {10, 1.5};
    connect("localhost", 8080);
    cache_put(1, d);
    Data cached = cache_get(1);
    double v = compute(cached);
    send_data(0, d);
    return 0;
}
