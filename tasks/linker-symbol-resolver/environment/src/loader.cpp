#include "linker/loader.h"
#include "json.h"

ObjectFile load_object_file(const std::string& /*path*/) {
    // TODO: parse JSON object file
    return {};
}

LinkConfig load_link_config(const std::string& /*path*/) {
    // TODO: parse JSON link config
    return {};
}

std::vector<ObjectFile> load_all_objects(const LinkConfig& /*config*/, const std::string& /*data_dir*/) {
    // TODO: load all object files listed in config
    return {};
}
