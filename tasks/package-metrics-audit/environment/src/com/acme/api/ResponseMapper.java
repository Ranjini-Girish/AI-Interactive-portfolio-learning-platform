package com.acme.api;

import com.acme.util.StringHelper;

public class ResponseMapper {

    public static String toJson(String key, Object value) {
        String v = value != null
                ? StringHelper.truncate(value.toString(), 1000)
                : "null";
        return "{\"" + key + "\": \"" + v + "\"}";
    }

    public static String errorResponse(int status, String message) {
        return "{\"error\": \"" + message + "\", \"status\": " + status + "}";
    }

    public static String successResponse(String data) {
        return "{\"success\": true, \"data\": " + data + "}";
    }
}
