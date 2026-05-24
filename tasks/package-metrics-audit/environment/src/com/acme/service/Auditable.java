package com.acme.service;

public interface Auditable {
    String getAuditLog();
    void clearAuditLog();
    long getAuditEntryCount();
}
