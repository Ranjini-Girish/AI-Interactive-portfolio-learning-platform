package com.acme.service;

import com.acme.core.Service;
import com.acme.model.Order;
import com.acme.model.OrderStatus;
import com.acme.persistence.OrderRepository;
import com.acme.notification.Notifier;

public class OrderService implements Service {
    private final OrderRepository repository;
    private final Notifier notifier;

    public OrderService(OrderRepository repository, Notifier notifier) {
        this.repository = repository;
        this.notifier = notifier;
    }

    @Override
    public void initialize() {}

    @Override
    public void shutdown() {}

    @Override
    public String getServiceName() {
        return "OrderService";
    }

    public void placeOrder(Order order) {
        order.setStatus(OrderStatus.CONFIRMED);
        repository.save(order);
        if (notifier.isAvailable()) {
            notifier.send(order.getUserId(),
                    "Order " + order.getId() + " confirmed");
        }
    }

    public void cancelOrder(String orderId) {
        repository.findById(orderId).ifPresent(order -> {
            if (!order.getStatus().isTerminal()) {
                order.setStatus(OrderStatus.CANCELLED);
                repository.save(order);
            }
        });
    }
}
