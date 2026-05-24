#include "mesh.h"
#include <fstream>
#include <sstream>
#include <cstdlib>
#include <cstring>
#include <stdexcept>

static std::string read_file(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) throw std::runtime_error("Cannot open: " + path);
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static double parse_double(const std::string& s) {
    return std::strtod(s.c_str(), nullptr);
}

static int parse_int(const std::string& s) {
    return std::atoi(s.c_str());
}

static std::string extract_value(const std::string& json, const std::string& key) {
    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return "";
    pos = json.find(':', pos);
    if (pos == std::string::npos) return "";
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\n')) pos++;
    if (json[pos] == '\"') {
        size_t end = json.find('\"', pos + 1);
        return json.substr(pos + 1, end - pos - 1);
    }
    size_t end = pos;
    while (end < json.size() && json[end] != ',' && json[end] != '}' && json[end] != ']' && json[end] != '\n') end++;
    return json.substr(pos, end - pos);
}

static std::vector<std::string> extract_array_objects(const std::string& json, const std::string& key) {
    std::vector<std::string> result;
    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return result;
    pos = json.find('[', pos);
    if (pos == std::string::npos) return result;
    pos++;
    int depth = 0;
    size_t start = std::string::npos;
    while (pos < json.size()) {
        if (json[pos] == '{') {
            if (depth == 0) start = pos;
            depth++;
        } else if (json[pos] == '}') {
            depth--;
            if (depth == 0 && start != std::string::npos) {
                result.push_back(json.substr(start, pos - start + 1));
                start = std::string::npos;
            }
        } else if (json[pos] == ']' && depth == 0) {
            break;
        }
        pos++;
    }
    return result;
}

static std::vector<int> extract_int_array(const std::string& json, const std::string& key) {
    std::vector<int> result;
    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return result;
    pos = json.find('[', pos);
    if (pos == std::string::npos) return result;
    size_t end = json.find(']', pos);
    std::string arr = json.substr(pos + 1, end - pos - 1);
    std::stringstream ss(arr);
    std::string token;
    while (std::getline(ss, token, ',')) {
        size_t s = token.find_first_of("0123456789");
        if (s != std::string::npos) result.push_back(parse_int(token.substr(s)));
    }
    return result;
}

MeshData load_mesh(const std::string& mesh_file, const std::string& config_file) {
    MeshData data;
    std::string mesh_json = read_file(mesh_file);
    std::string config_json = read_file(config_file);

    data.conductivity = parse_double(extract_value(mesh_json, "thermal_conductivity"));
    data.heat_source = parse_double(extract_value(mesh_json, "heat_source"));
    data.output_path = extract_value(mesh_json, "path");
    data.precision = parse_int(extract_value(mesh_json, "precision"));

    auto node_objs = extract_array_objects(mesh_json, "nodes");
    for (auto& obj : node_objs) {
        Node n;
        n.id = parse_int(extract_value(obj, "id"));
        n.x = parse_double(extract_value(obj, "x"));
        n.y = parse_double(extract_value(obj, "y"));
        data.nodes.push_back(n);
    }

    auto elem_objs = extract_array_objects(mesh_json, "elements");
    for (auto& obj : elem_objs) {
        Element e;
        e.id = parse_int(extract_value(obj, "id"));
        auto nids = extract_int_array(obj, "nodes");
        for (int k = 0; k < 3 && k < (int)nids.size(); k++) e.nodes[k] = nids[k];
        data.elements.push_back(e);
    }

    auto bc_objs = extract_array_objects(mesh_json, "dirichlet");
    for (auto& obj : bc_objs) {
        BoundaryCondition bc;
        bc.node_id = parse_int(extract_value(obj, "node_id"));
        bc.value = parse_double(extract_value(obj, "value"));
        data.dirichlet.push_back(bc);
    }

    return data;
}
