package com.acme.api;

public abstract class Controller {

    protected abstract String getBasePath();

    public String handleRequest(String method, String path) {
        if (!path.startsWith(getBasePath())) {
            return "{\"error\": \"not found\", \"status\": 404}";
        }
        return dispatch(method, path);
    }

    protected abstract String dispatch(String method, String path);

    public String healthCheck() {
        return "{\"status\": \"ok\"}";
    }
}
