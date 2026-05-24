#include "network.h"
#include "serializer.h"
#include "logger.h"

int connect(const char* host, int port) {
    log_message("connecting");
    return 0;
}

int send_data(int fd, const Data& d) {
    char buf[BUFFER_SIZE];
    serialize(d, buf);
    log_message("sending data");
    return 0;
}
