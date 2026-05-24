package com.acme.config;

import com.acme.core.Service;
import com.acme.service.UserService;

public class SecurityConfig {
    private final UserService userService;
    private final boolean enforceAuth;

    public SecurityConfig(UserService userService, boolean enforceAuth) {
        this.userService = userService;
        this.enforceAuth = enforceAuth;
    }

    public boolean isAuthorized(String userId) {
        if (!enforceAuth) return true;
        return userService.getUser(userId) != null;
    }

    public boolean isAuthEnabled() {
        return enforceAuth;
    }

    public Service getBackingService() {
        return (Service) userService;
    }
}
