#include "plugin_api.h"
#include "logger.h"

void* load_plugin(const char* name) {
    log_message("loading plugin");
    return nullptr;
}

void unload_plugin(void* handle) {
    log_message("unloading plugin");
}
