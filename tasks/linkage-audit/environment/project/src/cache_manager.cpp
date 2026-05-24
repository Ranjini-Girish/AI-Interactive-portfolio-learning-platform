#include "cache.h"
#include "logger.h"

static Data store[1024];

Data cache_get(int key) {
    log_message("cache hit");
    return store[key % 1024];
}

void cache_put(int key, const Data& d) {
    log_message("cache put");
    store[key % 1024] = d;
}

void cache_evict(int key) {
    log_message("cache evict");
    store[key % 1024] = {0, 0.0};
}
