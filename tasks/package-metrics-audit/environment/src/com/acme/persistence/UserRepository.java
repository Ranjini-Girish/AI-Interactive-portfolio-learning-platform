package com.acme.persistence;

import com.acme.core.Repository;
import com.acme.model.User;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class UserRepository implements Repository<User> {
    private final Map<String, User> store = new HashMap<>();

    @Override
    public Optional<User> findById(String id) {
        return Optional.ofNullable(store.get(id));
    }

    @Override
    public List<User> findAll() {
        return new ArrayList<>(store.values());
    }

    @Override
    public void save(User entity) {
        store.put(entity.getId(), entity);
    }

    @Override
    public void delete(String id) {
        store.remove(id);
    }

    public Optional<User> findByEmail(String email) {
        return store.values().stream()
                .filter(u -> email.equals(u.getEmail()))
                .findFirst();
    }
}
