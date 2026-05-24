package com.acme.core;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

public class IdGenerator {
    private static final AtomicLong counter = new AtomicLong(0);

    public static String generateUUID() {
        return UUID.randomUUID().toString();
    }

    public static String generateSequential(String prefix) {
        return prefix + "-" + counter.incrementAndGet();
    }

    public static void resetCounter() {
        counter.set(0);
    }
}
