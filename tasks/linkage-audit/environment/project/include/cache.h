#ifndef CACHE_H
#define CACHE_H

#include "types.h"

Data cache_get(int key);
void cache_put(int key, const Data& d);
void cache_evict(int key);

#endif
