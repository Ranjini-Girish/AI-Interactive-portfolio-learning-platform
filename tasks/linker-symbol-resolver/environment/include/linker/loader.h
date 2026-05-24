#pragma once
#include "types.h"
#include <string>
#include <vector>

ObjectFile load_object_file(const std::string& path);
LinkConfig load_link_config(const std::string& path);
std::vector<ObjectFile> load_all_objects(const LinkConfig& config, const std::string& data_dir);
