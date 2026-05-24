#pragma once
#include "types.h"
#include <map>
#include <vector>

struct ResolveResult {
    std::vector<SymbolEntry> symbols;
    std::vector<MergedSection> merged;
    std::map<std::string, int64_t> global_addrs;
    std::map<std::string, int64_t> section_bases;
    std::map<std::string, int64_t> local_addrs;
    std::vector<LinkError> errors;
    std::vector<LinkWarning> warnings;
    int64_t weak_count;
    int64_t entry_addr;
};

ResolveResult resolve(const std::vector<ObjectFile>& objects, const LinkConfig& config);
