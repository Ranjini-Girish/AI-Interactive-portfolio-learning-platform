package com.acme.util;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public class DateHelper {
    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    public static String formatISO(LocalDateTime dt) {
        return dt.format(ISO);
    }

    public static LocalDateTime parseISO(String s) {
        return LocalDateTime.parse(s, ISO);
    }

    public static long daysBetween(LocalDateTime from, LocalDateTime to) {
        return ChronoUnit.DAYS.between(from, to);
    }

    public static boolean isWithinHours(LocalDateTime dt, int hours) {
        return ChronoUnit.HOURS.between(dt, LocalDateTime.now()) <= hours;
    }
}
