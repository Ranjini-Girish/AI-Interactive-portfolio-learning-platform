#pragma once
#include <string>
#include <vector>
#include <map>
#include <cstdint>

struct Section {
    std::string name;
    int64_t size;
    int64_t alignment;
};

struct Symbol {
    std::string name;
    std::string section;
    int64_t offset = 0;
    int64_t size = 0;
    std::string binding;
    std::string type;
};

struct Relocation {
    std::string section;
    int64_t offset;
    std::string rel_type;
    std::string symbol;
    int64_t addend;
};

struct ObjectFile {
    std::string name;
    std::vector<Section> sections;
    std::vector<Symbol> symbols;
    std::vector<Relocation> relocations;
};

struct LinkConfig {
    int64_t base_address;
    std::vector<std::string> section_order;
    std::string entry_point;
    std::vector<std::string> object_files;
};

struct MergedContrib {
    std::string object_name;
    int64_t offset;
    int64_t size;
};

struct MergedSection {
    std::string name;
    int64_t address;
    int64_t total_size;
    int64_t alignment;
    std::vector<MergedContrib> contributions;
};

struct SymbolEntry {
    std::string name;
    int64_t address;
    int64_t size;
    std::string binding;
    std::string type;
    std::string source;
    std::string section;
};

struct AppliedReloc {
    std::string object_name;
    std::string section;
    int64_t offset;
    std::string rel_type;
    std::string symbol;
    int64_t symbol_address;
    int64_t value;
};

struct LinkError {
    std::string type;
    std::string symbol;
    std::string message;
    std::vector<std::string> objects;
};

struct LinkWarning {
    std::string type;
    std::string symbol;
    std::string object;
};

struct LinkResult {
    std::string status;
    int64_t entry_address;
    std::vector<MergedSection> sections;
    std::vector<SymbolEntry> symbols;
    std::vector<AppliedReloc> relocations;
    std::vector<LinkError> errors;
    std::vector<LinkWarning> warnings;
    int64_t total_objects;
    int64_t total_sections;
    int64_t total_symbols;
    int64_t weak_resolutions;
    int64_t total_relocs;
    int64_t total_size;
};
