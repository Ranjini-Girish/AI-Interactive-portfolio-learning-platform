package com.acme.persistence;

import com.acme.core.Repository;
import com.acme.model.Order;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

public class OrderRepository implements Repository<Order> {
    private final Map<String, Order> store = new HashMap<>();

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(store.get(id));
    }

    @Override
    public List<Order> findAll() {
        return new ArrayList<>(store.values());
    }

    @Override
    public void save(Order entity) {
        store.put(entity.getId(), entity);
    }

    @Override
    public void delete(String id) {
        store.remove(id);
    }

    public List<Order> findByUserId(String userId) {
        return store.values().stream()
                .filter(o -> userId.equals(o.getUserId()))
                .collect(Collectors.toList());
    }
}
