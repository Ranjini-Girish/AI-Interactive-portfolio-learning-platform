package com.acme.service;

import com.acme.model.Product;
import com.acme.persistence.ConnectionPool;

public class ProductService {
    private final ConnectionPool pool;

    public ProductService(ConnectionPool pool) {
        this.pool = pool;
    }

    public Product findProduct(String id) {
        if (!pool.acquire()) {
            throw new RuntimeException("No available connections");
        }
        try {
            return null;
        } finally {
            pool.release();
        }
    }

    public boolean isAvailable() {
        return pool.getActiveCount() < pool.getMaxRetries();
    }
}
