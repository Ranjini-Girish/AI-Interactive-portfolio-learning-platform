package com.acme.notification;

public interface Notifier {
    void send(String recipient, String message);
    boolean isAvailable();
    String getChannel();
}
