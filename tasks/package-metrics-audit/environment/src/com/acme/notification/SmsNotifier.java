package com.acme.notification;

import com.acme.service.Auditable;

public class SmsNotifier implements Notifier, Auditable {
    private final StringBuilder log = new StringBuilder();
    private long entryCount = 0;

    @Override
    public void send(String recipient, String message) {
        log.append("SMS to ").append(recipient)
           .append(": ").append(message).append("\n");
        entryCount++;
    }

    @Override
    public boolean isAvailable() {
        return false;
    }

    @Override
    public String getChannel() {
        return "sms";
    }

    @Override
    public String getAuditLog() {
        return log.toString();
    }

    @Override
    public void clearAuditLog() {
        log.setLength(0);
        entryCount = 0;
    }

    @Override
    public long getAuditEntryCount() {
        return entryCount;
    }
}
