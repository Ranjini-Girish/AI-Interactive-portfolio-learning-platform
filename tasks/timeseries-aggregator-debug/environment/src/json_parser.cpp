#include "json_parser.hpp"
#include <stdexcept>
#include <cctype>

double JsonValue::as_number() const { return std::get<double>(data_); }
int JsonValue::as_int() const { return static_cast<int>(std::get<double>(data_)); }
const std::string& JsonValue::as_string() const { return std::get<std::string>(data_); }
const JsonValue::Array& JsonValue::as_array() const { return std::get<Array>(data_); }
const JsonValue::Object& JsonValue::as_object() const { return std::get<Object>(data_); }

const JsonValue& JsonValue::operator[](const std::string& key) const {
    return std::get<Object>(data_).at(key);
}
const JsonValue& JsonValue::operator[](size_t idx) const {
    return std::get<Array>(data_).at(idx);
}

namespace {

size_t skip_ws(const std::string& s, size_t i) {
    while (i < s.size() && std::isspace(static_cast<unsigned char>(s[i]))) i++;
    return i;
}

JsonValue parse_value(const std::string& s, size_t& i);

std::string parse_string_val(const std::string& s, size_t& i) {
    i++;
    std::string result;
    while (i < s.size() && s[i] != '"') {
        if (s[i] == '\\') {
            i++;
            if (i < s.size()) {
                switch (s[i]) {
                    case '"':  result += '"';  break;
                    case '\\': result += '\\'; break;
                    case 'n':  result += '\n'; break;
                    case 't':  result += '\t'; break;
                    case '/':  result += '/';  break;
                    default:   result += s[i]; break;
                }
            }
        } else {
            result += s[i];
        }
        i++;
    }
    if (i < s.size()) i++;
    return result;
}

double parse_number(const std::string& s, size_t& i) {
    size_t start = i;
    if (s[i] == '-') i++;
    while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i]))) i++;
    if (i < s.size() && s[i] == '.') {
        i++;
        while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i]))) i++;
    }
    if (i < s.size() && (s[i] == 'e' || s[i] == 'E')) {
        i++;
        if (i < s.size() && (s[i] == '+' || s[i] == '-')) i++;
        while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i]))) i++;
    }
    return std::stod(s.substr(start, i - start));
}

JsonValue parse_value(const std::string& s, size_t& i) {
    i = skip_ws(s, i);
    if (i >= s.size()) throw std::runtime_error("Unexpected end of JSON");

    if (s[i] == '"') {
        return JsonValue(parse_string_val(s, i));
    }
    if (s[i] == '{') {
        i++;
        JsonValue::Object obj;
        i = skip_ws(s, i);
        while (i < s.size() && s[i] != '}') {
            i = skip_ws(s, i);
            std::string key = parse_string_val(s, i);
            i = skip_ws(s, i);
            if (i < s.size() && s[i] == ':') i++;
            obj[key] = parse_value(s, i);
            i = skip_ws(s, i);
            if (i < s.size() && s[i] == ',') i++;
        }
        if (i < s.size()) i++;
        return JsonValue(obj);
    }
    if (s[i] == '[') {
        i++;
        JsonValue::Array arr;
        i = skip_ws(s, i);
        while (i < s.size() && s[i] != ']') {
            arr.push_back(parse_value(s, i));
            i = skip_ws(s, i);
            if (i < s.size() && s[i] == ',') i++;
        }
        if (i < s.size()) i++;
        return JsonValue(arr);
    }
    if (std::isdigit(static_cast<unsigned char>(s[i])) || s[i] == '-') {
        return JsonValue(parse_number(s, i));
    }
    if (s.compare(i, 4, "true") == 0) { i += 4; return JsonValue(1.0); }
    if (s.compare(i, 5, "false") == 0) { i += 5; return JsonValue(0.0); }
    if (s.compare(i, 4, "null") == 0) { i += 4; return JsonValue(); }

    throw std::runtime_error("Invalid JSON at position " + std::to_string(i));
}

}

JsonValue parse_json(const std::string& input) {
    size_t i = 0;
    return parse_value(input, i);
}
