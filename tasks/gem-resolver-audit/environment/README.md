# Ruby Gem Dependency Resolver

A collection of Ruby gem registry data, project dependency manifests, security advisories, and license policy configuration.

## Directory Structure

- `data/registry/` — One JSON file per gem containing all published versions, their dependencies, and license info
- `data/projects/` — Four Ruby projects, each with a `Gemfile.json` declaring their dependencies
- `data/config/policy.json` — License compatibility rules, severity definitions, and risk scoring parameters
- `data/advisories/advisories.json` — Known security vulnerabilities with affected version ranges
- `docs/` — Specification documents describing the resolution algorithm and version constraint semantics
- `output/` — Write output here

## Gem Count

The registry contains 18 gems with a total of 62 published versions across them.

## Project Count

Four projects to audit: `api_service`, `web_app`, `worker`, `auth_lib`.
