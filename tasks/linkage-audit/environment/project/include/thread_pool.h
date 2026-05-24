#ifndef THREAD_POOL_H
#define THREAD_POOL_H

#include "cache.h"

void spawn_thread(void (*fn)(Data*));
void join_all();

#endif
