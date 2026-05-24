package com.acme.model;

import com.acme.core.Entity;
import java.util.List;
import java.util.ArrayList;

public class Order extends Entity {
    private final String userId;
    private final List<String> productIds;
    private OrderStatus status;
    private double totalAmount;

    public Order(String id, String userId) {
        super(id);
        this.userId = userId;
        this.productIds = new ArrayList<>();
        this.status = OrderStatus.PENDING;
        this.totalAmount = 0.0;
    }

    public String getUserId() {
        return userId;
    }

    public List<String> getProductIds() {
        return productIds;
    }

    public void addProduct(String productId) {
        productIds.add(productId);
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public double getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(double totalAmount) {
        this.totalAmount = totalAmount;
    }
}
