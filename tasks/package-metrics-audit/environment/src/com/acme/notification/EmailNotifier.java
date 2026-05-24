package com.acme.notification;

import com.acme.service.ValidationService;

public class EmailNotifier implements Notifier {
    private final ValidationService validator;

    public EmailNotifier(ValidationService validator) {
        this.validator = validator;
    }

    @Override
    public void send(String recipient, String message) {
        if (!validator.validateEmail(recipient)) {
            throw new IllegalArgumentException("Invalid email: " + recipient);
        }
        System.out.println("Email to " + recipient + ": " + message);
    }

    @Override
    public boolean isAvailable() {
        return true;
    }

    @Override
    public String getChannel() {
        return "email";
    }
}
