package com.acme.core;

public interface Service {
    void initialize();
    void shutdown();
    String getServiceName();
}
