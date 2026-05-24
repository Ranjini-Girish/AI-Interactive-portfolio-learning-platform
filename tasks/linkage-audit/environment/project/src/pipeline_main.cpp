#include "math_utils.h"
#include "string_utils.h"

extern void validate_a(const Data& d);
extern void validate_b(const Data& d);

int main() {
    Data d = {42, 3.14};
    validate_a(d);
    validate_b(d);
    return 0;
}
