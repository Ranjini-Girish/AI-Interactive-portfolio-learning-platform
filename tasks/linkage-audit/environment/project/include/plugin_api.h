#ifndef PLUGIN_API_H
#define PLUGIN_API_H

#include "types.h"
#include "config.h"

void* load_plugin(const char* name);
void unload_plugin(void* handle);

#endif
