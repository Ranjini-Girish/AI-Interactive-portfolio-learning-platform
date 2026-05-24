package com.acme.model;

public enum OrderStatus {
    PENDING("Awaiting confirmation"),
    CONFIRMED("Order confirmed"),
    SHIPPED("In transit"),
    DELIVERED("Delivered to customer"),
    CANCELLED("Order cancelled");

    private final String description;

    OrderStatus(String description) {
        this.description = description;
    }

    public String getDescription() {
        return description;
    }

    public boolean isTerminal() {
        return this == DELIVERED || this == CANCELLED;
    }
}
