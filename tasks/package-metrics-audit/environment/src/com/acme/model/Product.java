package com.acme.model;

import com.acme.core.Entity;

public class Product extends Entity {
    private String name;
    private double price;
    private int stockQuantity;

    public Product(String id, String name, double price) {
        super(id);
        this.name = name;
        this.price = price;
        this.stockQuantity = 0;
    }

    public String getName() {
        return name;
    }

    public double getPrice() {
        return price;
    }

    public void setPrice(double price) {
        this.price = price;
    }

    public int getStockQuantity() {
        return stockQuantity;
    }

    public void setStockQuantity(int stockQuantity) {
        this.stockQuantity = stockQuantity;
    }

    public boolean isInStock() {
        return stockQuantity > 0;
    }
}
