package com.acme.service;

import com.acme.model.User;
import com.acme.model.Order;

public class ValidationService {

    public boolean validateUser(User user) {
        if (user == null) return false;
        if (user.getName() == null || user.getName().isEmpty()) return false;
        if (user.getEmail() == null || !user.getEmail().contains("@")) return false;
        return true;
    }

    public boolean validateOrder(Order order) {
        if (order == null) return false;
        if (order.getUserId() == null) return false;
        if (order.getProductIds() == null || order.getProductIds().isEmpty()) return false;
        return true;
    }

    public boolean validateEmail(String email) {
        return email != null && email.matches("^[\\w.+-]+@[\\w.-]+\\.[a-zA-Z]{2,}$");
    }
}
