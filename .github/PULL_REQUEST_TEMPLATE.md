## Summary
<!-- 1-3 bullet points describing what this PR does -->

## Type
- [ ] feat: New feature
- [ ] fix: Bug fix
- [ ] refactor: Code change (no feature/fix)
- [ ] test: Adding tests
- [ ] docs: Documentation only
- [ ] chore: Build/tooling

## Module
<!-- Which module(s) does this touch? -->
- [ ] ingestion
- [ ] query
- [ ] agents / agent-observability
- [ ] apm
- [ ] infrastructure
- [ ] rum / synthetics
- [ ] alerting
- [ ] integrations
- [ ] logging
- [ ] frontend
- [ ] auth / security
- [ ] core / infra

## Checklist
- [ ] Tenant isolation: All queries include `tenant_id`
- [ ] No SQL injection: No string interpolation for user input in SQL
- [ ] Tests: Added/updated unit tests
- [ ] Types: No new mypy errors
- [ ] Lint: `make lint` passes

## Test Plan
<!-- How was this tested? -->
