package com.acme.persistence;

import com.acme.util.StringHelper;

public class QueryBuilder {
    private final StringBuilder query;

    public QueryBuilder(String table) {
        this.query = new StringBuilder("SELECT * FROM ").append(table);
    }

    public QueryBuilder where(String column, String value) {
        query.append(" WHERE ").append(column)
             .append(" = '")
             .append(StringHelper.truncate(value, 255))
             .append("'");
        return this;
    }

    public QueryBuilder orderBy(String column, boolean ascending) {
        query.append(" ORDER BY ").append(column);
        if (!ascending) query.append(" DESC");
        return this;
    }

    public QueryBuilder limit(int count) {
        query.append(" LIMIT ").append(count);
        return this;
    }

    public String build() {
        return query.toString();
    }
}
