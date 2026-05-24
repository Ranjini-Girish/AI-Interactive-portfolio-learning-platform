#pragma once
#include "types.h"
#include <map>
#include <vector>

std::vector<AppliedReloc> apply_relocations(
    const std::vector<ObjectFile>& objects,
    const std::map<std::string, int64_t>& global_addrs,
    const std::map<std::string, int64_t>& section_bases,
    const std::map<std::string, int64_t>& local_addrs);
