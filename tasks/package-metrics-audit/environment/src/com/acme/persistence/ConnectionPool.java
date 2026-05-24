package com.acme.persistence;

import com.acme.util.Constants;

public class ConnectionPool {
    private final int maxConnections;
    private int activeConnections;

    public ConnectionPool(int maxConnections) {
        this.maxConnections = maxConnections;
        this.activeConnections = 0;
    }

    public synchronized boolean acquire() {
        if (activeConnections >= maxConnections) return false;
        activeConnections++;
        return true;
    }

    public synchronized void release() {
        if (activeConnections > 0) activeConnections--;
    }

    public int getActiveCount() {
        return activeConnections;
    }

    public int getMaxRetries() {
        return Constants.MAX_RETRIES;
    }

    public long getTimeout() {
        return Constants.TIMEOUT_MS;
    }
}
