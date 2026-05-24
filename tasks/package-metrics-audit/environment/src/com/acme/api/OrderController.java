package com.acme.api;

import com.acme.service.OrderService;
import com.acme.model.Order;

public class OrderController extends Controller {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @Override
    protected String getBasePath() {
        return "/api/orders";
    }

    @Override
    protected String dispatch(String method, String path) {
        if ("POST".equals(method)) {
            return "{\"status\": \"order created\"}";
        }
        return "{\"orders\": []}";
    }
}
