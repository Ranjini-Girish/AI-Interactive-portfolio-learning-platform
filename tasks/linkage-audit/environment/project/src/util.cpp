static int internal_helper(int x) {
    return x * x + 1;
}

int parse_int(const char* s) {
    int result = 0;
    while (*s >= '0' && *s <= '9') {
        result = result * 10 + (*s - '0');
        s++;
    }
    return result;
}

char* trim_string(char* s) {
    while (*s == ' ') s++;
    return s;
}
