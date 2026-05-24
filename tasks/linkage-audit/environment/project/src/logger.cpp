#include "logger.h"
#include "config.h"

static int current_level = 0;

void log_message(const char* msg) {
    if (current_level > 0) {
        // write to log
    }
}

void set_log_level(int level) {
    current_level = level;
}
