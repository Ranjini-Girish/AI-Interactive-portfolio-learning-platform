#include "math_utils.h"
#include "string_utils.h"
#include "logger.h"
#include "serializer.h"

int main() {
    Data d = {1, 2.0};
    log_message("starting application");
    double r = compute(d);
    char* s = format_string(d);
    char buf[256];
    serialize(d, buf);
    return 0;
}
