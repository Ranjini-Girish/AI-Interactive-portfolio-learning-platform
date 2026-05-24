package com.acme.core;

import java.util.List;
import java.util.Optional;

public interface Repository<T extends Entity> {
    Optional<T> findById(String id);
    List<T> findAll();
    void save(T entity);
    void delete(String id);
}
