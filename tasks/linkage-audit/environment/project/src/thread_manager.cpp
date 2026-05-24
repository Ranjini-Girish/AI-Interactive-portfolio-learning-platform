#include "thread_pool.h"
#include "logger.h"

void spawn_thread(void (*fn)(Data*)) {
    log_message("spawning thread");
}

void join_all() {
    log_message("joining all threads");
}
