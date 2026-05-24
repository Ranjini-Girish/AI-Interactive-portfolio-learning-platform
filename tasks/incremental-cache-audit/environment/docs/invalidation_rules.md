# Invalidation Rules

The audit distinguishes production dirty crates from test-only dirty crates. Production propagation follows reverse `normal` and `build` dependencies for surface changes, never reverse `dev` dependencies. Private implementation changes are contained unless a direct reverse build dependency consumes the changed crate during its build.
