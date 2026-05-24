#pragma once
#include <map>
#include <string>
#include <variant>
#include <vector>

class JsonValue {
public:
    using Object = std::map<std::string, JsonValue>;
    using Array = std::vector<JsonValue>;

    JsonValue() = default;
    explicit JsonValue(double d) : data_(d) {}
    explicit JsonValue(const std::string& s) : data_(s) {}
    explicit JsonValue(const Array& a) : data_(a) {}
    explicit JsonValue(const Object& o) : data_(o) {}

    bool is_number() const { return std::holds_alternative<double>(data_); }
    bool is_string() const { return std::holds_alternative<std::string>(data_); }
    bool is_array() const { return std::holds_alternative<Array>(data_); }
    bool is_object() const { return std::holds_alternative<Object>(data_); }

    double as_number() const;
    int as_int() const;
    const std::string& as_string() const;
    const Array& as_array() const;
    const Object& as_object() const;

    const JsonValue& operator[](const std::string& key) const;
    const JsonValue& operator[](size_t idx) const;

private:
    std::variant<std::monostate, double, std::string, Array, Object> data_;
};

JsonValue parse_json(const std::string& input);
