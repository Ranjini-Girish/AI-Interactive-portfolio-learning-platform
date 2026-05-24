#ifndef NETWORK_H
#define NETWORK_H

#include "config.h"
#include "types.h"

int connect(const char* host, int port);
int send_data(int fd, const Data& d);

#endif
