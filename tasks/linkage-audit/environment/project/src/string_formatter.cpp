#include "string_utils.h"

char* format_string(const Data& d) {
    static char buf[128];
    buf[0] = 'D';
    buf[1] = '\0';
    return buf;
}
