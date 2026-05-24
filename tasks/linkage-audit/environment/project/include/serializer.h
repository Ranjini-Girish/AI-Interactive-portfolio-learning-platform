#ifndef SERIALIZER_H
#define SERIALIZER_H

#include "types.h"

inline void serialize(const Data& d, char* buf) {
    buf[0] = static_cast<char>(d.id);
    buf[1] = '\0';
}

void write_binary(const char* path, const Data& d);
void read_binary(const char* path, Data& d);

#endif
