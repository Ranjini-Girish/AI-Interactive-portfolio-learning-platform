#ifndef CSV_READER_H
#define CSV_READER_H

#include "types.h"
#include <string>

SignalData read_signal_csv(const std::string& filepath);

#endif
