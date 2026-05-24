package com.acme.service;

import com.acme.core.Service;
import com.acme.model.User;
import com.acme.persistence.UserRepository;

public class UserService implements Service {
    private final UserRepository repository;
    private boolean initialized;

    public UserService(UserRepository repository) {
        this.repository = repository;
        this.initialized = false;
    }

    @Override
    public void initialize() {
        initialized = true;
    }

    @Override
    public void shutdown() {
        initialized = false;
    }

    @Override
    public String getServiceName() {
        return "UserService";
    }

    public User getUser(String id) {
        if (!initialized) throw new IllegalStateException("Service not initialized");
        return repository.findById(id).orElse(null);
    }

    public void createUser(String id, String name, String email) {
        repository.save(new User(id, name, email));
    }
}
