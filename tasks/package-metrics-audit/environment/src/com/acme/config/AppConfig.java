package com.acme.config;

import com.acme.core.IdGenerator;

public class AppConfig {
    private final String appId;
    private final String environment;
    private final boolean debugMode;

    public AppConfig(String environment) {
        this.appId = IdGenerator.generateUUID();
        this.environment = environment;
        this.debugMode = "dev".equals(environment);
    }

    public String getAppId() {
        return appId;
    }

    public String getEnvironment() {
        return environment;
    }

    public boolean isDebugMode() {
        return debugMode;
    }

    public boolean isProduction() {
        return "prod".equals(environment);
    }
}
