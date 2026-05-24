# Acme Commerce Platform

Multi-package Java application for e-commerce operations.

## Project Structure

Source code is organized under `src/com/acme/` with the following packages:

- `core` — Base abstractions (Entity, Repository, Service)
- `model` — Domain model (User, Order, Product, Address, OrderStatus)
- `util` — Utility helpers (StringHelper, DateHelper, MathHelper, Constants)
- `persistence` — Data access (repositories, connection pooling, query building)
- `service` — Business logic (user, order, product, validation services)
- `notification` — Notification channels (email, SMS)
- `api` — REST controllers and response mapping
- `config` — Application and security configuration

## Build

Requires Java 21+.
