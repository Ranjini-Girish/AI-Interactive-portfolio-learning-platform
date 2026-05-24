package com.acme.util;

public class Constants {
    public static final int MAX_RETRIES = 3;
    public static final long TIMEOUT_MS = 5000L;
    public static final String DEFAULT_CHARSET = "UTF-8";
    public static final int PAGE_SIZE = 50;
    public static final double EPSILON = 1e-9;

    private Constants() {
        throw new UnsupportedOperationException("Utility class");
    }
}
