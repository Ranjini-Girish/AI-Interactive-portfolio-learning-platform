# License Compliance Rules

## SPDX Expression Parsing

Compound SPDX expressions use parentheses with OR or AND operators.

**OR expressions**: `(MIT OR GPL-3.0-only)` means the consumer may choose
either license. Choose the one whose policy category is most permissive
(allowed > restricted > banned). If tied, pick the alphabetically first.

**AND expressions**: `(MIT AND BSD-2-Clause)` means all licenses apply.
The effective license string is the combined form (`MIT AND BSD-2-Clause`).
The effective category is the most restrictive among the components.

## Copyleft Propagation

When a package has a copyleft license (GPL-2.0-only, GPL-3.0-only,
AGPL-3.0-only), every package that depends on it — directly or
transitively — receives a `copyleft_propagation` violation.

LGPL licenses with dynamic linking are exempt from propagation when the
policy flag `lgpl_dynamic_linking_exempt` is true. These packages still
generate their own `restricted_license` violations but do not infect
their dependents.

## Waivers

A waiver exempts a specific package in a specific project. The violation
is still recorded (with `waived: true`) but excluded from the risk score.
Waivers do not extend to other projects using the same package.
