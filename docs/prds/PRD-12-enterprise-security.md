# PRD-12: Multi-Tenancy, RBAC & Enterprise Security

**Product**: RayOlly — AI-Native Observability Platform
**Version**: 1.0
**Date**: 2026-03-19
**Status**: Draft
**Parent**: PRD-00 Platform Vision & Architecture
**Dependencies**: PRD-01 (Ingestion), PRD-02 (Storage), PRD-03 (Query Engine), PRD-05 (API Gateway)
**Author**: Security & Platform Architecture Team
**Stakeholders**: Engineering, Security, Compliance, Legal, SRE, Executive Leadership

---

## 1. Executive Summary

Enterprise adoption of observability platforms demands rigorous security, compliance, and access control guarantees. PRD-12 defines RayOlly's multi-tenancy architecture, authentication and authorization framework, data protection mechanisms, and compliance posture. This is the foundational security PRD that every other module depends on — no data enters or leaves RayOlly without passing through the systems described here.

**Key Capabilities**:
- **Multi-tenancy** with Organization > Team > Project hierarchy and strict data isolation on shared infrastructure
- **Authentication** via email/password with MFA, SAML 2.0, OIDC, SCIM 2.0 provisioning, and service accounts
- **Fine-grained RBAC** with built-in roles, custom roles, field-level access control, and data masking
- **API security** with scoped API keys, OAuth2 client credentials, rate limiting, IP allowlisting, and request signing
- **Data security** with AES-256 encryption at rest, TLS 1.3 in transit, PII redaction, and secrets detection
- **Audit logging** with immutable, searchable audit trails retained for 7 years
- **Compliance** readiness for SOC 2 Type II, HIPAA, GDPR, and FedRAMP

**Why This Matters**: Without this PRD, RayOlly cannot sell to any enterprise with more than 50 engineers. Security and compliance are table-stakes for the $500K+ ACV deals that fund the platform.

---

## 2. Goals & Non-Goals

### 2.1 Goals

| ID | Goal | Success Criteria |
|----|------|-----------------|
| G1 | Zero cross-tenant data leakage | Formal verification of tenant isolation; zero incidents in pen testing |
| G2 | SSO integration in < 30 minutes | Customer can configure SAML/OIDC and have users logging in within 30 min |
| G3 | Fine-grained RBAC | Permissions controllable down to field-level on any resource |
| G4 | SOC 2 Type II certification | Pass audit within 6 months of GA |
| G5 | HIPAA readiness | BAA-ready with PHI handling controls at GA |
| G6 | GDPR compliance | Full data subject rights (erasure, portability, consent) at GA |
| G7 | Sub-100ms auth overhead | Authentication and authorization add < 100ms p99 to any request |
| G8 | Immutable audit logging | Tamper-proof audit trail for all administrative and data-access actions |
| G9 | Automated PII detection | Detect and redact PII in ingested telemetry data before storage |
| G10 | Self-service security admin | Org admins can manage users, roles, keys, and policies without RayOlly support |

### 2.2 Non-Goals

- **Build a full IAM product** — We integrate with existing IdPs, not replace them
- **Custom encryption algorithms** — We use industry-standard primitives (AES-256, RSA-2048, Ed25519)
- **Real-time SIEM** — Security event analysis on customer telemetry is a separate module (future)
- **Physical security** — Handled by cloud providers (AWS, GCP, Azure) and SOC 2 inherited controls
- **FedRAMP certification at GA** — Readiness only; certification is a 12-month post-GA effort
- **On-premise HSM support** — Cloud KMS only at GA; HSM support in v2

---

## 3. Multi-Tenancy Architecture

### 3.1 Organization Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                       Organization                           │
│  (Billing entity, SSO config, compliance settings)           │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Team: SRE  │  │ Team: Backend│  │ Team: Mobile │      │
│  │              │  │              │  │              │      │
│  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │      │
│  │ │Project:  │ │  │ │Project:  │ │  │ │Project:  │ │      │
│  │ │ prod-k8s │ │  │ │ payments │ │  │ │ ios-app  │ │      │
│  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │      │
│  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │      │
│  │ │Project:  │ │  │ │Project:  │ │  │ │Project:  │ │      │
│  │ │ staging  │ │  │ │ auth-svc │ │  │ │ android  │ │      │
│  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

**Entity Definitions**:

| Entity | Description | Limits |
|--------|-------------|--------|
| **Organization** | Top-level billing and security boundary. Maps to a company or business unit. Owns SSO config, compliance settings, and billing. | 1 per account |
| **Team** | Logical grouping of users within an org. Maps to engineering teams. Owns shared dashboards, alerts, and notification channels. | Up to 500 per org |
| **Project** | Data isolation boundary. All telemetry (logs, metrics, traces) is scoped to a project. Maps to a service, environment, or application. | Up to 1,000 per org |
| **User** | An authenticated identity (human or service). Belongs to one org, can be a member of multiple teams. | Up to 10,000 per org |

### 3.2 Data Isolation Model

RayOlly uses **shared infrastructure with logical data isolation** — all tenants share the same compute and storage clusters, but data is strictly partitioned at the storage and query layers.

```
┌─────────────────────────────────────────────────────────────┐
│                    Shared Infrastructure                      │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              API Gateway / Load Balancer              │    │
│  │          (Tenant ID extracted from JWT/API key)       │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                          │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │               Tenant Context Middleware               │    │
│  │  • Validates tenant_id from auth token                │    │
│  │  • Injects tenant_id into request context             │    │
│  │  • Enforces that tenant_id cannot be overridden       │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                          │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │                  Query Engine                         │    │
│  │  • Appends WHERE org_id = ? AND project_id = ?        │    │
│  │  • Enforced at query planner level (cannot bypass)    │    │
│  │  • Cross-tenant JOIN is architecturally impossible     │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                          │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │          ClickHouse / Object Storage                  │    │
│  │  • Partitioned by (org_id, project_id, date)          │    │
│  │  • Row-level security policies                        │    │
│  │  • Separate encryption keys per org (optional)        │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Tenant Identification and Routing

Every request carries a tenant context derived from the authentication token:

```json
{
  "tenant_context": {
    "org_id": "org_a1b2c3d4",
    "user_id": "usr_x7y8z9",
    "teams": ["team_sre", "team_platform"],
    "active_project": "proj_prod_k8s",
    "roles": ["org:editor", "team_sre:admin", "proj_prod_k8s:editor"],
    "permissions": ["logs:read", "logs:write", "metrics:read", "dashboards:*"]
  }
}
```

**Routing rules**:
- `org_id` is immutable and derived from the JWT `sub` claim at authentication time
- `project_id` is specified per request (header `X-RayOlly-Project` or query parameter)
- The middleware validates the user has access to the requested project
- All downstream services receive the validated tenant context — they never trust client-supplied `org_id`

### 3.4 Cross-Tenant Query Prevention

| Layer | Mechanism |
|-------|-----------|
| **API Gateway** | Extracts `org_id` from JWT; rejects requests without valid tenant context |
| **Query Engine** | Mandatory `org_id` + `project_id` filter injected at query planning — the query planner refuses to execute without it |
| **ClickHouse** | Row-level security policies enforce `org_id` filtering at the storage layer as a defense-in-depth measure |
| **Object Storage** | S3 bucket policies restrict access by prefix `s3://rayolly-data/{org_id}/` |
| **Cache** | Redis key namespace includes `org_id` prefix; cache isolation by key structure |
| **CI/CD Testing** | Automated cross-tenant access tests run on every deployment |

### 3.5 Resource Quotas and Fair Use

```yaml
# Example: Organization Quota Configuration
org_quotas:
  tier: enterprise
  ingestion:
    logs_gb_per_day: 500
    metrics_series: 1_000_000
    traces_spans_per_sec: 50_000
  storage:
    hot_retention_days: 30
    warm_retention_days: 90
    cold_retention_days: 365
    total_storage_tb: 50
  query:
    concurrent_queries: 100
    max_query_duration_sec: 300
    max_scan_bytes_per_query: 10_737_418_240  # 10 GB
  api:
    requests_per_minute: 10_000
    burst_size: 1_000
  users:
    max_users: 10_000
    max_teams: 500
    max_projects: 1_000
    max_api_keys: 500
```

### 3.6 Noisy Neighbor Prevention

| Mechanism | Description |
|-----------|-------------|
| **Ingestion rate limiting** | Per-org token bucket with configurable burst. Excess data queued, not dropped, with backpressure signals. |
| **Query resource pools** | Each org gets a dedicated ClickHouse resource pool with CPU/memory limits. Heavy queries cannot starve other tenants. |
| **Priority queues** | Queries classified as interactive (< 10s), analytical (< 5min), or batch (< 30min). Interactive queries get priority. |
| **Circuit breakers** | If an org exceeds 80% of its query quota, new queries are throttled with HTTP 429 and `Retry-After` header. |
| **Storage compaction isolation** | Background compaction jobs are scheduled per-org to prevent I/O contention. |

### 3.7 Database-Level Isolation Strategy

**ClickHouse**:
- All tables include `org_id` and `project_id` as the first columns in the primary key / partition key
- Partition by `(org_id, toYYYYMM(timestamp))` for efficient data lifecycle management
- Row-level security policies attached to all user-facing tables
- Materialized views are scoped to `org_id`

**PostgreSQL (metadata)**:
- Shared database with per-org schema isolation for sensitive metadata
- Row-level security (RLS) enabled on all tenant-scoped tables
- Connection pooling with tenant-aware routing (PgBouncer with `org_id` in application_name)

**Redis (cache)**:
- Key namespace: `{org_id}:{resource_type}:{resource_id}`
- Separate Redis logical databases not used (they don't scale); instead, key-prefix isolation with Lua scripts

**Object Storage (S3/GCS)**:
- Path-based isolation: `s3://rayolly-data/{org_id}/{project_id}/{data_type}/{date}/`
- Bucket policies restrict IAM roles to org-specific prefixes
- Customer-managed encryption keys per org (optional)

---

## 4. Authentication

### 4.1 Authentication Methods Overview

| Method | Use Case | MFA Support | SSO | Self-Service |
|--------|----------|-------------|-----|-------------|
| Email/Password | Default for small teams | TOTP, WebAuthn | No | Yes |
| SAML 2.0 | Enterprise SSO (Okta, Azure AD, OneLogin) | Delegated to IdP | Yes | Admin-configured |
| OIDC | Developer SSO (Google, GitHub, Auth0, Keycloak) | Delegated to IdP | Yes | Admin-configured |
| API Key | Service-to-service, CI/CD | N/A | N/A | Yes |
| Service Account | Machine-to-machine with RBAC | N/A | N/A | Admin-configured |
| OAuth2 Client Credentials | Programmatic access with scoped tokens | N/A | N/A | Admin-configured |

### 4.2 Built-In Email/Password with MFA

**Password Policy** (configurable per org):
- Minimum 12 characters (default), configurable up to 128
- At least 1 uppercase, 1 lowercase, 1 digit, 1 special character
- Bcrypt hashing with cost factor 12 (adjustable)
- Password history: last 10 passwords cannot be reused
- Account lockout after 5 failed attempts (30-minute lockout, configurable)
- Breach database check against HaveIBeenPwned API (k-anonymity model)

**MFA Options**:

| Type | Standard | Description |
|------|----------|-------------|
| **TOTP** | RFC 6238 | Time-based one-time passwords (Google Authenticator, Authy, 1Password) |
| **WebAuthn/FIDO2** | W3C WebAuthn L2 | Hardware security keys (YubiKey), platform authenticators (Touch ID, Windows Hello) |
| **Recovery Codes** | — | 10 single-use recovery codes generated at MFA enrollment |

**MFA Enforcement**:
- Org admins can mandate MFA for all users
- MFA required for all Owner and Admin roles (non-optional)
- Grace period: 7 days after account creation to enroll MFA before access is restricted

### 4.3 SAML 2.0 SSO

**Supported Identity Providers**:
- Okta (verified integration)
- Azure Active Directory / Entra ID (verified integration)
- OneLogin (verified integration)
- PingFederate (verified integration)
- Any SAML 2.0-compliant IdP (generic integration)

**SAML Configuration**:

```yaml
sso:
  saml:
    entity_id: "https://auth.rayolly.com/saml/{org_slug}"
    acs_url: "https://auth.rayolly.com/saml/{org_slug}/acs"
    slo_url: "https://auth.rayolly.com/saml/{org_slug}/slo"
    metadata_url: "https://auth.rayolly.com/saml/{org_slug}/metadata"
    name_id_format: "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    signature_algorithm: "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
    want_assertions_signed: true
    want_assertions_encrypted: true
    attribute_mapping:
      email: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
      first_name: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname"
      last_name: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname"
      groups: "http://schemas.xmlsoap.org/claims/Group"
```

### 4.4 OIDC SSO

**Supported Providers**:
- Google Workspace
- GitHub (Organization-scoped)
- Auth0
- Keycloak
- Any OIDC-compliant provider

**OIDC Configuration**:

```yaml
sso:
  oidc:
    issuer: "https://accounts.google.com"
    client_id: "${OIDC_CLIENT_ID}"
    client_secret: "${OIDC_CLIENT_SECRET}"  # stored encrypted in Vault
    redirect_uri: "https://app.rayolly.com/auth/callback"
    scopes: ["openid", "profile", "email", "groups"]
    response_type: "code"
    grant_type: "authorization_code"
    pkce: true  # Always use PKCE
    token_endpoint_auth_method: "client_secret_post"
    claim_mapping:
      email: "email"
      name: "name"
      groups: "groups"
```

### 4.5 SCIM 2.0 Provisioning

SCIM enables automatic user and group synchronization between the identity provider and RayOlly.

**Supported Operations**:

| SCIM Resource | Operations | Behavior |
|---------------|-----------|----------|
| `/Users` | GET, POST, PUT, PATCH, DELETE | Create/update/deactivate users. Deactivated users lose access immediately. |
| `/Groups` | GET, POST, PUT, PATCH, DELETE | Create/update/delete teams. Group membership maps to RayOlly team membership. |
| `/Schemas` | GET | Returns RayOlly's SCIM schema extensions |
| `/ServiceProviderConfig` | GET | Returns SCIM capabilities |
| `/Bulk` | POST | Batch operations for initial provisioning |

**SCIM Endpoint**: `https://api.rayolly.com/scim/v2/{org_slug}/`

**User Lifecycle**:
1. User created in IdP -> SCIM POST creates user in RayOlly (status: pending)
2. User assigned to groups in IdP -> SCIM PATCH adds user to teams in RayOlly
3. User removed from IdP -> SCIM DELETE deactivates user, revokes all active sessions within 60 seconds
4. User re-enabled in IdP -> SCIM PATCH reactivates user with previous team memberships

### 4.6 Service Accounts and API Keys

**Service Accounts**:
- Machine identity, not tied to a human user
- Assigned roles and permissions like regular users
- Cannot log in via UI — API-only access
- Created by org admins, owned by a team
- Automatically audited (all actions logged)

**API Keys**:
- Scoped to a project and a set of permissions
- Format: `ro_live_` + 40-char random string (live keys) / `ro_test_` + 40-char (test keys)
- Stored as SHA-256 hash — plaintext shown once at creation, never again
- Expiry: configurable (default 90 days, max 365 days, no-expiry for Enterprise)
- Rotation: new key generated before old key expires; grace period for overlap

### 4.7 Session Management

```
┌──────────┐       ┌──────────────┐       ┌──────────────┐
│  Client   │──────▶│  Auth Service │──────▶│   IdP (SSO)  │
│ (Browser) │       │              │       │              │
└──────┬───┘       └──────┬───────┘       └──────────────┘
       │                   │
       │  ┌────────────────▼────────────────┐
       │  │  On successful authentication:   │
       │  │                                  │
       │  │  1. Issue access_token (JWT)     │
       │  │     - Signed with Ed25519        │
       │  │     - TTL: 15 minutes            │
       │  │     - Contains: user_id, org_id, │
       │  │       roles, permissions          │
       │  │                                  │
       │  │  2. Issue refresh_token           │
       │  │     - Opaque, stored in DB       │
       │  │     - TTL: 7 days (configurable) │
       │  │     - Rotated on each use        │
       │  │     - Bound to device fingerprint│
       │  │                                  │
       │  │  3. Set HTTP-only secure cookie   │
       │  │     - SameSite=Strict            │
       │  │     - Domain-locked              │
       │  └──────────────────────────────────┘
       │
       │  Token refresh flow:
       ▼
  access_token expired?
       │
       ├── YES ──▶ POST /auth/refresh
       │           { refresh_token, device_id }
       │           └──▶ Validate refresh_token
       │               └──▶ Issue new access_token + rotate refresh_token
       │
       └── NO ──▶ Proceed with request
```

**Session Security Properties**:
- Access tokens are short-lived (15 min) to limit blast radius of token theft
- Refresh tokens are rotated on every use (refresh token rotation)
- Refresh token reuse detection: if a refresh token is used twice, all sessions for that user are invalidated (breach signal)
- Sessions can be listed and revoked individually via the admin UI
- Concurrent session limit: configurable per org (default: 10 per user)
- Idle timeout: 30 minutes of inactivity (configurable)

### 4.8 Auth Flow Diagrams

**SAML 2.0 SP-Initiated Flow**:

```
┌────────┐         ┌──────────────┐         ┌───────────┐
│ Browser │         │ RayOlly Auth │         │  IdP      │
│         │         │   Service    │         │ (Okta)    │
└────┬───┘         └──────┬───────┘         └─────┬─────┘
     │                     │                       │
     │  1. GET /app        │                       │
     │────────────────────▶│                       │
     │                     │                       │
     │  2. 302 Redirect    │                       │
     │     to IdP SSO URL  │                       │
     │◀────────────────────│                       │
     │                     │                       │
     │  3. GET /sso/saml   │                       │
     │     (with SAMLReq)  │                       │
     │─────────────────────┼──────────────────────▶│
     │                     │                       │
     │  4. User authenticates at IdP               │
     │◀────────────────────┼───────────────────────│
     │                     │                       │
     │  5. POST /saml/acs  │                       │
     │     (SAMLResponse)  │                       │
     │────────────────────▶│                       │
     │                     │                       │
     │                     │  6. Validate signature │
     │                     │     Extract attributes │
     │                     │     Create/update user │
     │                     │     Map groups->teams  │
     │                     │     Issue JWT tokens   │
     │                     │                       │
     │  7. 302 /app        │                       │
     │     Set-Cookie: JWT │                       │
     │◀────────────────────│                       │
     │                     │                       │
```

**API Key Authentication Flow**:

```
┌────────────┐         ┌──────────────┐         ┌────────────┐
│ Client/CI  │         │ API Gateway  │         │ Auth Cache  │
└─────┬──────┘         └──────┬───────┘         └─────┬──────┘
      │                       │                        │
      │  1. Request with      │                        │
      │  Authorization:       │                        │
      │  Bearer ro_live_xxx   │                        │
      │──────────────────────▶│                        │
      │                       │                        │
      │                       │ 2. Hash(key) lookup    │
      │                       │───────────────────────▶│
      │                       │                        │
      │                       │ 3. Return: org_id,     │
      │                       │    scopes, rate limits  │
      │                       │◀───────────────────────│
      │                       │                        │
      │                       │ 4. Validate:           │
      │                       │    - Not expired        │
      │                       │    - Not revoked        │
      │                       │    - IP allowed         │
      │                       │    - Scope matches      │
      │                       │    - Rate limit OK      │
      │                       │                        │
      │  5. 200 OK / 403      │                        │
      │◀──────────────────────│                        │
```

---

## 5. Authorization (RBAC)

### 5.1 Role-Based Access Control Model

RayOlly implements a hierarchical RBAC model with three levels of scope:

```
Organization Scope
    └── Team Scope
          └── Project Scope
                └── Resource Scope (optional, for field-level control)
```

Permissions are **additive** — a user's effective permissions are the union of all permissions granted by all their roles across all scopes. There are no explicit "deny" rules; instead, the absence of a permission means denial (default-deny model).

### 5.2 Built-In Roles

| Role | Scope | Description | Typical User |
|------|-------|-------------|-------------|
| **Owner** | Org | Full control. Can delete org, manage billing, configure SSO. Only 1-3 per org. | CTO, VP Eng |
| **Admin** | Org or Team | Manage users, teams, roles, and settings within scope. Cannot delete org or manage billing. | Engineering Manager, Team Lead |
| **Editor** | Org, Team, or Project | Create and modify resources (dashboards, alerts, saved queries). Can ingest data. | Senior Engineer, SRE |
| **Viewer** | Org, Team, or Project | Read-only access to all data and resources within scope. Cannot create or modify. | Junior Engineer, Stakeholder |
| **Billing** | Org | Access to billing, usage, and invoicing. No access to telemetry data. | Finance, Procurement |

### 5.3 Permission Model (Resource-Action Matrix)

Permissions follow the format: `{resource_type}:{action}`

| Resource Type | read | write | create | delete | admin | export |
|---------------|:----:|:-----:|:------:|:------:|:-----:|:------:|
| **logs** | V | E | E | A | A | E |
| **metrics** | V | E | E | A | A | E |
| **traces** | V | E | E | A | A | E |
| **dashboards** | V | E | E | E | A | E |
| **alerts** | V | E | E | E | A | — |
| **saved_queries** | V | E | E | E | A | E |
| **notebooks** | V | E | E | E | A | E |
| **service_map** | V | — | — | — | A | V |
| **slos** | V | E | E | E | A | — |
| **users** | A | A | A | O | O | — |
| **teams** | A | A | A | A | O | — |
| **projects** | A | A | A | A | O | — |
| **roles** | A | A | A | O | O | — |
| **api_keys** | E | E | E | E | A | — |
| **audit_logs** | A | — | — | — | O | A |
| **billing** | B | B | — | — | O | B |
| **settings** | A | A | — | — | O | — |
| **integrations** | A | A | A | A | O | — |
| **data_masks** | A | A | A | A | O | — |

**Legend**: O = Owner, A = Admin, E = Editor, V = Viewer, B = Billing, — = Not applicable

### 5.4 Custom Roles

Org admins can create custom roles with arbitrary permission sets:

```json
{
  "role": {
    "name": "security-auditor",
    "display_name": "Security Auditor",
    "description": "Read-only access to audit logs and security settings",
    "scope": "organization",
    "permissions": [
      "audit_logs:read",
      "audit_logs:export",
      "settings:read",
      "users:read",
      "teams:read",
      "roles:read",
      "api_keys:read"
    ],
    "constraints": {
      "ip_allowlist": ["10.0.0.0/8", "172.16.0.0/12"],
      "time_restriction": {
        "timezone": "America/New_York",
        "allowed_hours": { "start": "09:00", "end": "18:00" },
        "allowed_days": ["mon", "tue", "wed", "thu", "fri"]
      },
      "mfa_required": true
    }
  }
}
```

### 5.5 Scope Hierarchy and Permission Inheritance

```
org:admin (granted at org level)
  ├── Applies to ALL teams in the org
  ├── Applies to ALL projects in the org
  └── Includes all admin-level permissions on all resources

team:editor (granted at team level)
  ├── Applies to ALL projects owned by this team
  └── Includes all editor-level permissions on team resources

project:viewer (granted at project level)
  └── Includes all viewer-level permissions on this project only
```

**Inheritance rules**:
1. Org-level roles cascade to all teams and projects
2. Team-level roles cascade to all projects owned by the team
3. Project-level roles apply only to that project
4. A user can have different roles at different scopes (e.g., org:viewer + team_sre:admin)
5. The most permissive role wins when scopes overlap (additive model)

### 5.6 Field-Level Access Control

For sensitive data, RayOlly supports field-level permissions that restrict which fields a user can see:

```yaml
field_access_policies:
  - name: "hide-pii-from-viewers"
    description: "Viewers cannot see PII fields in logs"
    applies_to:
      roles: ["viewer"]
      scope: "organization"
    rules:
      - resource: "logs"
        hidden_fields:
          - "user.email"
          - "user.ip_address"
          - "user.phone"
          - "request.headers.authorization"
          - "request.headers.cookie"
        masked_fields:
          - field: "user.name"
            mask: "hash"  # Shows SHA-256 hash instead of value
          - field: "user.id"
            mask: "partial"  # Shows last 4 characters: "****5678"

  - name: "restrict-financial-data"
    description: "Only finance team can see billing-related log fields"
    applies_to:
      roles: ["viewer", "editor"]
      excluded_teams: ["finance"]
    rules:
      - resource: "logs"
        hidden_fields:
          - "transaction.amount"
          - "transaction.card_last_four"
          - "transaction.account_number"
```

### 5.7 Data Masking Rules

| Mask Type | Example Input | Example Output | Use Case |
|-----------|--------------|----------------|----------|
| `redact` | `john@example.com` | `[REDACTED]` | Complete removal |
| `hash` | `john@example.com` | `a1b2c3d4e5f6...` | Correlation without exposure |
| `partial` | `4111111111111111` | `****1111` | Partial visibility |
| `tokenize` | `john@example.com` | `tok_x7y8z9` | Reversible by authorized users |
| `generalize` | `192.168.1.42` | `192.168.1.0/24` | Reduce precision |
| `noise` | `35` (age) | `30-40` (range) | Statistical privacy |

### 5.8 Example RBAC Configuration

```json
{
  "org": "acme-corp",
  "users": [
    {
      "email": "alice@acme.com",
      "roles": [
        { "role": "owner", "scope": "org:acme-corp" }
      ]
    },
    {
      "email": "bob@acme.com",
      "roles": [
        { "role": "admin", "scope": "team:sre" },
        { "role": "viewer", "scope": "team:backend" }
      ]
    },
    {
      "email": "charlie@acme.com",
      "roles": [
        { "role": "editor", "scope": "project:prod-k8s" },
        { "role": "viewer", "scope": "project:staging" }
      ]
    },
    {
      "email": "diana@acme.com",
      "roles": [
        { "role": "security-auditor", "scope": "org:acme-corp" }
      ]
    },
    {
      "email": "finance-bot@acme.com",
      "type": "service_account",
      "roles": [
        { "role": "billing", "scope": "org:acme-corp" }
      ]
    }
  ]
}
```

**Effective permissions for Bob**:
- On team `sre` projects: full admin (manage users, create/edit/delete resources)
- On team `backend` projects: read-only (view dashboards, query logs, view alerts)
- On all other projects: no access

---

## 6. API Security

### 6.1 API Key Management

**Key Lifecycle**:

```
Create ──▶ Active ──▶ Expiring Soon (< 14 days) ──▶ Expired
                │                                        │
                ├── Revoked (manual)                     │
                │                                        │
                └── Rotated (new key created, old key    │
                    enters grace period of 24h) ─────────┘
```

**API Key Create Request**:

```bash
curl -X POST https://api.rayolly.com/v1/api-keys \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ci-cd-pipeline",
    "scopes": ["logs:write", "metrics:write"],
    "project_id": "proj_prod_k8s",
    "expires_in_days": 90,
    "ip_allowlist": ["10.0.0.0/8"],
    "rate_limit": {
      "requests_per_minute": 1000
    }
  }'
```

**Response** (plaintext key shown only once):

```json
{
  "id": "key_a1b2c3d4",
  "key": "ro_live_k8sJ3xMnPqR7tUvWyZ2aB4cD6eF8gH0iJkLmNoPqRsTuVwXy",
  "name": "ci-cd-pipeline",
  "prefix": "ro_live_k8sJ",
  "scopes": ["logs:write", "metrics:write"],
  "project_id": "proj_prod_k8s",
  "created_at": "2026-03-19T10:00:00Z",
  "expires_at": "2026-06-17T10:00:00Z",
  "created_by": "usr_x7y8z9"
}
```

### 6.2 OAuth2 Client Credentials

For service-to-service communication where a service needs to act on behalf of an org:

```bash
# Request token
curl -X POST https://auth.rayolly.com/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "scope=logs:write metrics:write" \
  -d "audience=https://api.rayolly.com"

# Response
{
  "access_token": "eyJhbGciOiJFZERTQSIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "logs:write metrics:write"
}
```

### 6.3 Rate Limiting

| Tier | Requests/min | Burst | Concurrent Queries | Ingestion Rate |
|------|-------------|-------|-------------------|---------------|
| Free | 100 | 20 | 5 | 1 GB/day |
| Team | 1,000 | 200 | 25 | 50 GB/day |
| Business | 5,000 | 1,000 | 50 | 200 GB/day |
| Enterprise | 10,000+ | 2,000+ | 100+ | Custom |

Rate limit headers on every response:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1710849600
X-RateLimit-Policy: "1000;w=60"
Retry-After: 12  (only on 429 responses)
```

### 6.4 IP Allowlisting

```json
{
  "ip_policy": {
    "name": "corporate-network-only",
    "scope": "organization",
    "mode": "allowlist",
    "rules": [
      { "cidr": "10.0.0.0/8", "description": "Internal network" },
      { "cidr": "203.0.113.0/24", "description": "VPN egress" },
      { "cidr": "198.51.100.50/32", "description": "CI/CD runner" }
    ],
    "enforcement": {
      "api_keys": true,
      "ui_sessions": false,
      "service_accounts": true
    },
    "bypass": {
      "roles": ["owner"],
      "require_mfa": true
    }
  }
}
```

### 6.5 Request Signing

For high-security environments, RayOlly supports HMAC request signing (similar to AWS Signature V4):

```
Authorization: RAYOLLY-HMAC-SHA256
  Credential={key_id}/{date}/{region}/rayolly/request,
  SignedHeaders=host;x-rayolly-date;x-rayolly-content-sha256,
  Signature={hex(HMAC-SHA256(signing_key, string_to_sign))}
```

The signing process:
1. Create canonical request (method, path, query, headers, body hash)
2. Create string to sign (algorithm, timestamp, credential scope, hash of canonical request)
3. Derive signing key from API key secret using HMAC chain
4. Compute signature

---

## 7. Data Security

### 7.1 Encryption at Rest

| Data Store | Algorithm | Key Management | Rotation |
|-----------|-----------|---------------|----------|
| ClickHouse | AES-256-GCM | AWS KMS / GCP Cloud KMS | Automatic, 90 days |
| PostgreSQL | AES-256-CBC (TDE) | AWS KMS / GCP Cloud KMS | Automatic, 90 days |
| Object Storage (S3/GCS) | AES-256-GCM (SSE-KMS) | AWS KMS / GCP Cloud KMS | Automatic, 365 days |
| Redis | At-rest encryption (ElastiCache/Memorystore) | AWS KMS / GCP Cloud KMS | Automatic, 90 days |
| Backups | AES-256-GCM | Separate backup KMS key | Automatic, 90 days |

**Customer-Managed Keys (CMK)**:
- Enterprise customers can bring their own KMS keys
- RayOlly uses the customer's key via KMS grants (never accesses the key material)
- Customer can revoke the grant to make their data permanently inaccessible (crypto-shred)
- Supported: AWS KMS, GCP Cloud KMS, Azure Key Vault

### 7.2 Encryption in Transit

| Communication Path | Protocol | Minimum Version | Cipher Suites |
|-------------------|----------|----------------|---------------|
| Client to API | TLS | 1.3 | TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256 |
| Client to UI | TLS | 1.3 | Same as above |
| Service to service (internal) | mTLS | 1.3 | Same + certificate pinning |
| Service to ClickHouse | mTLS | 1.3 | TLS_AES_256_GCM_SHA384 |
| Service to PostgreSQL | TLS | 1.3 | TLS_AES_256_GCM_SHA384 |
| Service to Redis | TLS | 1.2+ | TLS_AES_256_GCM_SHA384 |

**Certificate Management**:
- Public certificates: Let's Encrypt with auto-renewal (cert-manager in K8s)
- Internal mTLS: SPIFFE/SPIRE for workload identity and automatic certificate rotation
- Certificate rotation: every 24 hours for internal mTLS, 90 days for public TLS

### 7.3 PII Detection and Redaction Pipeline

```
┌──────────┐    ┌─────────────┐    ┌──────────────┐    ┌───────────┐
│ Ingestion │───▶│ PII Scanner │───▶│ Redaction    │───▶│ Storage   │
│ Pipeline  │    │             │    │ Engine       │    │           │
└──────────┘    │ • Regex     │    │ • Apply mask │    └───────────┘
                │ • NER model │    │ • Log action │
                │ • Custom    │    │ • Preserve   │
                │   patterns  │    │   structure  │
                └─────────────┘    └──────────────┘
```

**Built-in PII Detectors**:

| PII Type | Detection Method | Default Action | Confidence Threshold |
|----------|-----------------|----------------|---------------------|
| Email addresses | Regex + validation | `hash` | 0.95 |
| Phone numbers | Regex (libphonenumber) | `redact` | 0.90 |
| SSN | Regex + checksum | `redact` | 0.99 |
| Credit card numbers | Regex + Luhn check | `redact` | 0.99 |
| IP addresses (private) | Regex | `generalize` | 0.99 |
| AWS access keys | Regex (`AKIA*`) | `redact` | 0.99 |
| JWT tokens | Regex (`eyJ*`) | `redact` | 0.95 |
| Names (person) | NER model | `hash` | 0.80 |
| Addresses | NER model | `redact` | 0.75 |
| Custom patterns | User-defined regex | Configurable | Configurable |

### 7.4 Data Classification

| Level | Label | Examples | Access | Retention |
|-------|-------|---------|--------|-----------|
| 1 | **Public** | Service status, public API docs | All authenticated users | Standard |
| 2 | **Internal** | Application logs, metrics, traces | Team members with Viewer+ | Standard |
| 3 | **Confidential** | Audit logs, user data, access logs | Admins only | Extended (3yr) |
| 4 | **Restricted** | Encryption keys, credentials, PHI | Owners + explicit grant | Maximum (7yr) |

### 7.5 Data Loss Prevention Rules

```yaml
dlp_rules:
  - name: "block-credential-exfiltration"
    description: "Prevent export of data containing credentials"
    trigger: "export"
    conditions:
      - field_matches:
          pattern: "(password|secret|token|api_key|private_key)"
          case_insensitive: true
    action: "block"
    notification:
      channels: ["security-alerts"]
      severity: "critical"

  - name: "restrict-pii-export"
    description: "PII data export requires admin approval"
    trigger: "export"
    conditions:
      - data_classification: "confidential"
      - contains_pii: true
    action: "require_approval"
    approvers: ["role:admin", "role:owner"]
    notification:
      channels: ["compliance-team"]
```

### 7.6 Secrets Detection in Logs

RayOlly scans all incoming log data for accidentally leaked secrets:

| Secret Type | Pattern | Action |
|-------------|---------|--------|
| AWS Access Key | `AKIA[0-9A-Z]{16}` | Redact + alert |
| AWS Secret Key | 40-char base64 near access key | Redact + alert |
| GitHub Token | `ghp_[a-zA-Z0-9]{36}` | Redact + alert |
| GitLab Token | `glpat-[a-zA-Z0-9\-]{20}` | Redact + alert |
| Slack Token | `xox[bpars]-[a-zA-Z0-9-]+` | Redact + alert |
| Private Key | `-----BEGIN (RSA|EC|DSA) PRIVATE KEY-----` | Redact + critical alert |
| Generic API Key | High-entropy string near keyword `api_key`, `secret`, `token` | Flag for review |
| Database URL | `(postgres|mysql|mongodb)://.*:.*@` | Redact + alert |

---

## 8. Audit Logging

### 8.1 Comprehensive Audit Trail

Every significant action in RayOlly produces an immutable audit log entry. Audit logs answer: **Who** did **what**, **when**, from **where**, and **why** (if context is available).

**Audited Events**:

| Category | Events |
|----------|--------|
| **Authentication** | Login success/failure, logout, MFA enrollment/removal, password change, session creation/revocation |
| **User Management** | User create/update/deactivate/delete, role assignment/removal, team membership change |
| **Data Access** | Query execution (who queried what data), dashboard view, log export, API data access |
| **Configuration** | Alert rule create/update/delete, dashboard create/update/delete, integration config change |
| **Security** | API key create/revoke/rotate, SSO config change, IP policy change, data masking rule change |
| **Admin** | Org settings change, billing change, quota adjustment, compliance setting change |
| **System** | SCIM sync events, automated actions by AI agents, scheduled report execution |

### 8.2 Audit Log Schema

```json
{
  "id": "audit_01HQ3X5K7M9N2P4R6S8T0V",
  "timestamp": "2026-03-19T14:32:15.123Z",
  "event_type": "user.role.assigned",
  "category": "user_management",
  "severity": "info",
  "actor": {
    "id": "usr_alice_a1b2",
    "email": "alice@acme.com",
    "type": "user",
    "ip_address": "203.0.113.50",
    "user_agent": "Mozilla/5.0 ...",
    "geo": {
      "country": "US",
      "region": "California",
      "city": "San Francisco"
    },
    "session_id": "sess_x7y8z9"
  },
  "org_id": "org_acme",
  "target": {
    "type": "user",
    "id": "usr_bob_c3d4",
    "email": "bob@acme.com"
  },
  "action": {
    "type": "assign_role",
    "details": {
      "role": "admin",
      "scope": "team:sre",
      "previous_role": "editor"
    }
  },
  "result": "success",
  "request": {
    "method": "POST",
    "path": "/v1/users/usr_bob_c3d4/roles",
    "request_id": "req_m5n6o7p8"
  },
  "metadata": {
    "change_reason": "Promoted to team lead",
    "approval_ticket": "JIRA-1234"
  }
}
```

### 8.3 Immutable Audit Log Storage

- Audit logs are written to an **append-only** storage backend
- Production: AWS S3 with Object Lock (WORM — Write Once, Read Many) in Compliance mode
- No API exists to delete or modify audit log entries — not even for Owner role
- Integrity verification: each audit log entry includes a SHA-256 hash chain linking it to the previous entry
- Daily integrity checks validate the hash chain
- Cross-region replication for disaster recovery

### 8.4 Audit Log Search and Export

```bash
# Search audit logs via API
curl "https://api.rayolly.com/v1/audit-logs" \
  -H "Authorization: Bearer ${TOKEN}" \
  -G \
  -d "event_type=user.role.assigned" \
  -d "actor.email=alice@acme.com" \
  -d "start_time=2026-03-01T00:00:00Z" \
  -d "end_time=2026-03-19T23:59:59Z" \
  -d "limit=100"

# Export audit logs for compliance
curl -X POST "https://api.rayolly.com/v1/audit-logs/export" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "format": "csv",
    "date_range": { "start": "2026-01-01", "end": "2026-03-31" },
    "categories": ["authentication", "user_management", "security"],
    "delivery": {
      "method": "s3",
      "bucket": "acme-compliance-exports",
      "prefix": "rayolly/audit/"
    }
  }'
```

### 8.5 Compliance Report Generation

Pre-built compliance reports:

| Report | Content | Schedule |
|--------|---------|----------|
| **User Access Review** | All users, their roles, last login, permissions | Monthly |
| **Privileged Access Report** | All Owner/Admin role assignments and changes | Weekly |
| **Failed Login Report** | All failed authentication attempts with source IPs | Daily |
| **Data Access Report** | Who accessed what data, query volumes by user | Monthly |
| **API Key Audit** | All API keys, their scopes, usage, expiry status | Weekly |
| **Configuration Change Report** | All security-relevant config changes | Weekly |
| **SCIM Sync Report** | User provisioning/deprovisioning events | Daily |

### 8.6 Retention

- Audit logs are retained for **7 years** (configurable, minimum 1 year)
- Hot storage (searchable via UI): 90 days
- Warm storage (searchable via API, slower): 1 year
- Cold storage (exported to customer's S3, retrievable on request): 7 years
- Retention cannot be reduced below regulatory minimums (SOC 2: 1 year, HIPAA: 6 years, GDPR: as needed)

---

## 9. Compliance

### 9.1 SOC 2 Type II

**Control Categories and RayOlly Implementation**:

| Trust Service Criteria | Control | RayOlly Implementation | Evidence |
|----------------------|---------|----------------------|----------|
| **Security (CC6)** | Logical access controls | RBAC with MFA, SSO | Auth logs, role config |
| **Security (CC6)** | Encryption | AES-256 at rest, TLS 1.3 in transit | KMS config, TLS certs |
| **Security (CC7)** | System monitoring | Self-monitoring with RayOlly itself | Dashboards, alerts |
| **Security (CC8)** | Change management | CI/CD with approval gates, IaC | Git history, PR approvals |
| **Availability (A1)** | System availability | 99.9% SLA, multi-AZ, DR plan | Uptime dashboards |
| **Availability (A1)** | Disaster recovery | Cross-region replication, RTO < 4h | DR runbooks, test results |
| **Confidentiality (C1)** | Data classification | 4-level classification system | Classification policies |
| **Confidentiality (C1)** | Data disposal | Crypto-shred on org deletion | Deletion audit logs |
| **Processing Integrity (PI1)** | Data accuracy | Checksum validation on ingestion | Pipeline metrics |
| **Privacy (P1-P8)** | PII handling | Detection, redaction, consent management | DLP policy config |

**SOC 2 Evidence Collection**: RayOlly automatically collects evidence for SOC 2 audits via the compliance dashboard, reducing audit preparation time from weeks to hours.

### 9.2 HIPAA

**Business Associate Agreement (BAA)**: RayOlly offers a BAA for Enterprise tier customers who process Protected Health Information (PHI).

| HIPAA Requirement | RayOlly Implementation |
|-------------------|----------------------|
| Access controls (164.312(a)) | RBAC with MFA, audit logging, automatic session timeout |
| Audit controls (164.312(b)) | Immutable audit logs, 7-year retention, tamper detection |
| Integrity controls (164.312(c)) | Data checksums, hash chain verification, TLS in transit |
| Transmission security (164.312(e)) | TLS 1.3 for all data in transit, mTLS for internal |
| Encryption (164.312(a)(2)(iv)) | AES-256 at rest, customer-managed keys |
| Person authentication (164.312(d)) | MFA mandatory for PHI access, SSO with IdP |
| PHI minimum necessary | Field-level access control, data masking rules |
| Breach notification | Automated detection, 60-day notification procedures |
| Disposal | Crypto-shred on data deletion, verified purge |

**PHI Handling**:
- PHI fields are automatically detected and tagged during ingestion
- Access to PHI-tagged fields requires explicit `phi:read` permission
- All PHI access is logged in the audit trail with elevated detail
- PHI data masking is enabled by default for Viewer and Editor roles
- PHI data cannot be exported without Owner approval and audit trail

### 9.3 GDPR

| GDPR Requirement | RayOlly Implementation |
|------------------|----------------------|
| **Lawful basis (Art. 6)** | Data Processing Agreement (DPA) for customers; consent management for end users |
| **Right to access (Art. 15)** | API to export all personal data for a given data subject |
| **Right to erasure (Art. 17)** | API to delete all data associated with a data subject; crypto-shred capability |
| **Right to portability (Art. 20)** | Data export in JSON and CSV formats |
| **Data minimization (Art. 5)** | PII redaction pipeline, configurable retention policies |
| **Data protection by design (Art. 25)** | Encryption, pseudonymization, access controls built-in |
| **Breach notification (Art. 33)** | 72-hour notification capability; automated detection |
| **DPO support (Art. 37)** | Compliance dashboard with GDPR-specific reports |
| **Cross-border transfers (Art. 46)** | EU data residency option, Standard Contractual Clauses (SCCs) |
| **Records of processing (Art. 30)** | Automated ROPA generation from system metadata |

**Data Subject Access Request (DSAR) API**:

```bash
# Search for all data associated with a data subject
curl -X POST "https://api.rayolly.com/v1/compliance/dsar" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "request_type": "access",
    "subject_identifiers": {
      "email": "user@example.com",
      "user_id": "ext_user_123"
    },
    "date_range": { "start": "2025-01-01", "end": "2026-03-19" },
    "callback_url": "https://acme.com/webhooks/dsar"
  }'

# Request erasure of all data for a data subject
curl -X POST "https://api.rayolly.com/v1/compliance/dsar" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "request_type": "erasure",
    "subject_identifiers": {
      "email": "user@example.com"
    },
    "verification": {
      "method": "admin_approval",
      "approver": "usr_alice_a1b2"
    }
  }'
```

### 9.4 FedRAMP Readiness (Future)

FedRAMP certification is planned for 12 months post-GA. Readiness activities at GA:

- [ ] FIPS 140-2 validated cryptographic modules
- [ ] Continuous monitoring (ConMon) infrastructure
- [ ] System Security Plan (SSP) draft
- [ ] Plan of Action and Milestones (POA&M) template
- [ ] Incident response plan aligned with US-CERT
- [ ] Boundary definition and data flow diagrams
- [ ] Supply chain risk management (SCRM) plan

### 9.5 PCI DSS

For customers who ingest payment-related logs:

| PCI DSS Requirement | RayOlly Implementation |
|--------------------|----------------------|
| Req 3: Protect stored data | AES-256 encryption, automatic PAN detection and masking |
| Req 4: Encrypt transmission | TLS 1.3 for all data in transit |
| Req 7: Restrict access | RBAC with least-privilege, need-to-know enforcement |
| Req 8: Identify and authenticate | MFA, unique user IDs, password policies |
| Req 10: Track and monitor | Immutable audit logs for all access to cardholder data |
| Req 12: Security policy | Documented security policies, annual review |

**Automatic PAN Detection**: Credit card numbers (Primary Account Numbers) are detected using regex with Luhn checksum validation and automatically redacted before storage.

### 9.6 Compliance Dashboard

The compliance dashboard provides a real-time view of compliance posture:

```
┌─────────────────────────────────────────────────────────────┐
│  Compliance Dashboard                                        │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  SOC 2      │  │  HIPAA      │  │  GDPR       │         │
│  │  ██████░░   │  │  ████████░  │  │  ██████████ │         │
│  │  78% Ready  │  │  92% Ready  │  │  100% Ready │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                              │
│  Recent Compliance Events:                                   │
│  • [INFO]  DSAR request completed (erasure) - 2h ago        │
│  • [WARN]  3 users without MFA enrolled - action needed     │
│  • [INFO]  Quarterly access review completed - 1d ago       │
│  • [OK]    Audit log integrity check passed - 6h ago        │
│  • [WARN]  API key "staging-deploy" expires in 7 days       │
│                                                              │
│  Upcoming:                                                   │
│  • Annual penetration test - scheduled Apr 15                │
│  • SOC 2 Type II audit - scheduled May 1                    │
│  • Quarterly access review - due Apr 1                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 10. Network Security

### 10.1 VPC Peering / PrivateLink (SaaS)

For enterprise customers who require private connectivity to RayOlly SaaS:

| Cloud | Service | Description |
|-------|---------|-------------|
| **AWS** | PrivateLink | RayOlly exposes VPC endpoint services; customer creates interface endpoints in their VPC |
| **GCP** | Private Service Connect | Customer connects to RayOlly via PSC endpoint |
| **Azure** | Private Link | Customer creates private endpoint in their VNET |

**Benefits**: Traffic never traverses the public internet; reduced attack surface; compatible with customer's network security policies.

### 10.2 Network Policies (Self-Hosted)

For self-hosted deployments on Kubernetes:

```yaml
# Example: Restrict API server ingress
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: rayolly-api-ingress
  namespace: rayolly
spec:
  podSelector:
    matchLabels:
      app: rayolly-api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: rayolly-ingress
        - podSelector:
            matchLabels:
              app: rayolly-gateway
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: rayolly-clickhouse
      ports:
        - protocol: TCP
          port: 9440  # ClickHouse TLS
    - to:
        - podSelector:
            matchLabels:
              app: rayolly-postgres
      ports:
        - protocol: TCP
          port: 5432
    - to:  # DNS
        - namespaceSelector: {}
      ports:
        - protocol: UDP
          port: 53
```

### 10.3 WAF Integration

RayOlly SaaS runs behind a Web Application Firewall with the following protections:

| Rule Set | Protection |
|----------|-----------|
| OWASP Core Rule Set (CRS) | SQL injection, XSS, LFI, RFI, command injection |
| Rate limiting | Per-IP and per-tenant request rate limits |
| Geo-blocking | Configurable country-level blocking per org |
| Bot detection | Challenge-based bot mitigation for UI; token validation for API |
| Custom rules | Org-specific WAF rules (Enterprise tier) |

### 10.4 DDoS Protection

| Layer | Protection | Provider |
|-------|-----------|----------|
| L3/L4 | Volumetric attack mitigation (up to 1 Tbps) | AWS Shield Advanced / Cloudflare |
| L7 | Application-layer flood protection | WAF rate limiting + adaptive throttling |
| DNS | DNS amplification protection | Route 53 / Cloudflare DNS |
| Anycast | Global traffic distribution | Cloudflare / AWS Global Accelerator |

### 10.5 Ingress/Egress Controls

**Ingress**:
- All traffic enters through the load balancer / WAF
- Direct access to internal services is blocked
- Admin endpoints (`/admin`, `/internal`) restricted to VPN CIDRs
- Health check endpoints excluded from authentication

**Egress**:
- Internal services can only reach defined external endpoints (allowlist)
- Egress to customer webhook URLs validated against blocklist (no internal IPs, no cloud metadata)
- All egress logged for security monitoring
- DNS filtering to prevent data exfiltration via DNS tunneling

---

## 11. Vulnerability Management

### 11.1 Container Image Scanning

```yaml
# CI/CD pipeline - Trivy scanning
- name: Scan container image
  run: |
    trivy image \
      --severity HIGH,CRITICAL \
      --exit-code 1 \
      --ignore-unfixed \
      --format sarif \
      --output trivy-results.sarif \
      rayolly/api-server:${GIT_SHA}
```

**Policy**: No container image with HIGH or CRITICAL vulnerabilities is deployed to production. Images are rescanned weekly in the registry.

### 11.2 Dependency Scanning

| Tool | Scope | Frequency | Action on Critical |
|------|-------|-----------|-------------------|
| Dependabot | Go modules, npm, Python | Daily | Auto-PR with fix |
| Snyk | All dependencies + license compliance | Every commit | Block merge |
| `govulncheck` | Go standard library | Every build | Block deploy |
| npm audit | Frontend dependencies | Every build | Block deploy |

### 11.3 SAST/DAST in CI/CD

| Type | Tool | Scope | Gate |
|------|------|-------|------|
| SAST | Semgrep | All application code | Block merge on high/critical |
| SAST | gosec | Go-specific security checks | Block merge on high/critical |
| DAST | OWASP ZAP | Staging environment endpoints | Block promotion to prod |
| Secret scanning | Gitleaks | All commits | Block push |
| IaC scanning | Checkov | Terraform, Kubernetes manifests | Block merge on high/critical |

### 11.4 Penetration Testing Program

- **Frequency**: Annual third-party pen test (minimum), plus quarterly internal red team exercises
- **Scope**: Full application, infrastructure, and API testing
- **Standard**: OWASP Testing Guide v4, PTES
- **Remediation SLA**: Critical — 24h, High — 7 days, Medium — 30 days, Low — 90 days
- **Reports**: Shared with customers under NDA upon request (Enterprise tier)

### 11.5 Bug Bounty Program

- **Platform**: HackerOne (or equivalent)
- **Scope**: `*.rayolly.com`, API endpoints, SDKs
- **Rewards**: $250 (Low) to $15,000 (Critical)
- **Safe harbor**: Researchers protected under responsible disclosure policy
- **Response SLA**: Acknowledge within 24h, triage within 72h

---

## 12. Incident Response for Security

### 12.1 Security Incident Response Plan

| Phase | Actions | SLA |
|-------|---------|-----|
| **Detection** | Automated alerts from SIEM, audit log anomaly detection, customer reports, bug bounty | Real-time |
| **Triage** | On-call security engineer assesses severity, impact, and blast radius | 15 min (P1), 1h (P2) |
| **Containment** | Isolate affected systems, revoke compromised credentials, block attack vectors | 1h (P1), 4h (P2) |
| **Eradication** | Remove root cause, patch vulnerabilities, rotate all affected secrets | 24h (P1), 72h (P2) |
| **Recovery** | Restore normal operations, verify integrity, re-enable services | 48h (P1) |
| **Post-mortem** | Root cause analysis, timeline reconstruction, remediation items, process improvements | 5 business days |

**Severity Classification**:

| Severity | Definition | Example |
|----------|-----------|---------|
| P1 - Critical | Active exploitation, data breach, cross-tenant access | Unauthorized data access, credential leak |
| P2 - High | Vulnerability with clear exploit path, no active exploitation | SQL injection found, auth bypass possible |
| P3 - Medium | Vulnerability requiring significant effort to exploit | CSRF in non-critical endpoint |
| P4 - Low | Informational, hardening opportunity | Missing security header |

### 12.2 Breach Notification Procedures

| Regulation | Notification Deadline | Who to Notify |
|-----------|----------------------|---------------|
| GDPR | 72 hours to supervisory authority | DPA, affected data subjects if high risk |
| HIPAA | 60 days to HHS; without unreasonable delay to individuals | HHS, affected individuals, media (if > 500) |
| SOC 2 | As defined in customer contract | Affected customers |
| State laws (US) | Varies (24h to 60 days depending on state) | Affected individuals, state AG |

**Breach notification template** and communication runbooks are maintained and tested quarterly.

### 12.3 Forensic Logging

During a security incident, additional forensic logging is activated:

- Full request/response body logging (normally not stored)
- Network flow logs at packet level
- Process-level system call auditing (auditd/eBPF)
- Database query logging with full parameter values
- All logs shipped to a separate, isolated forensic storage (not accessible to regular admins)
- Chain of custody maintained for legal proceedings

---

## 13. Frontend Components

### 13.1 Admin Panel for User/Team/Role Management

**Users Page** (`/settings/users`):
- List all users in the org with search, filter by role/team/status
- Invite new users (email + role assignment)
- Bulk operations (assign role, deactivate, remove)
- View user details: roles, teams, last login, MFA status, active sessions

**Teams Page** (`/settings/teams`):
- Create/edit/delete teams
- Manage team membership (add/remove users)
- Assign team-level roles
- View team's projects and resources

**Roles Page** (`/settings/roles`):
- View built-in roles with their permissions
- Create/edit/delete custom roles
- Permission matrix editor (checkbox grid: resource x action)
- Role assignment history

### 13.2 API Key Management UI

**API Keys Page** (`/settings/api-keys`):
- List all API keys: name, prefix, scopes, project, created by, last used, expiry
- Create new key with scope selector and IP allowlist
- Revoke keys (with confirmation and reason)
- Rotate keys (generates new key, old key has 24h grace period)
- Usage metrics per key (requests/day, last 30 days chart)
- Expiry warnings (highlighted in yellow < 14 days, red < 3 days)

### 13.3 Audit Log Viewer

**Audit Logs Page** (`/settings/audit-logs`):
- Real-time streaming view of audit events
- Filters: event type, actor, target, date range, severity, result (success/failure)
- Full-text search across audit log content
- Detail panel: click an event to see full JSON payload
- Export: CSV, JSON, or direct to S3
- Saved filters for common compliance queries

### 13.4 Security Settings Page

**Security Page** (`/settings/security`):
- SSO configuration (SAML/OIDC setup wizard)
- MFA enforcement policy
- Password policy configuration
- Session timeout settings
- IP allowlist management
- Data masking rules
- PII detection settings
- Compliance dashboard (embedded)

---

## 14. API Endpoints

### 14.1 User Management API

| Method | Endpoint | Description | Required Role |
|--------|---------|-------------|--------------|
| GET | `/v1/users` | List users in org | Admin |
| POST | `/v1/users/invite` | Invite user by email | Admin |
| GET | `/v1/users/{user_id}` | Get user details | Admin |
| PATCH | `/v1/users/{user_id}` | Update user properties | Admin |
| DELETE | `/v1/users/{user_id}` | Deactivate user | Owner |
| POST | `/v1/users/{user_id}/mfa/enforce` | Force MFA enrollment | Admin |
| GET | `/v1/users/{user_id}/sessions` | List active sessions | Admin |
| DELETE | `/v1/users/{user_id}/sessions/{session_id}` | Revoke session | Admin |

### 14.2 Team/Organization Management API

| Method | Endpoint | Description | Required Role |
|--------|---------|-------------|--------------|
| GET | `/v1/org` | Get org details | Viewer |
| PATCH | `/v1/org` | Update org settings | Owner |
| GET | `/v1/teams` | List teams | Viewer |
| POST | `/v1/teams` | Create team | Admin |
| GET | `/v1/teams/{team_id}` | Get team details | Viewer |
| PATCH | `/v1/teams/{team_id}` | Update team | Admin |
| DELETE | `/v1/teams/{team_id}` | Delete team | Admin |
| POST | `/v1/teams/{team_id}/members` | Add member | Admin |
| DELETE | `/v1/teams/{team_id}/members/{user_id}` | Remove member | Admin |
| GET | `/v1/projects` | List projects | Viewer |
| POST | `/v1/projects` | Create project | Admin |
| DELETE | `/v1/projects/{project_id}` | Delete project | Owner |

### 14.3 Role/Permission API

| Method | Endpoint | Description | Required Role |
|--------|---------|-------------|--------------|
| GET | `/v1/roles` | List all roles (built-in + custom) | Admin |
| POST | `/v1/roles` | Create custom role | Admin |
| GET | `/v1/roles/{role_id}` | Get role details + permissions | Admin |
| PATCH | `/v1/roles/{role_id}` | Update custom role | Admin |
| DELETE | `/v1/roles/{role_id}` | Delete custom role | Owner |
| POST | `/v1/users/{user_id}/roles` | Assign role to user | Admin |
| DELETE | `/v1/users/{user_id}/roles/{role_id}` | Remove role from user | Admin |
| GET | `/v1/permissions` | List all available permissions | Admin |
| POST | `/v1/permissions/check` | Check if user has permission | Any |

**Permission Check Example**:

```bash
curl -X POST "https://api.rayolly.com/v1/permissions/check" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "user_id": "usr_bob_c3d4",
    "permission": "logs:read",
    "resource": {
      "type": "project",
      "id": "proj_prod_k8s"
    }
  }'

# Response
{
  "allowed": true,
  "reason": "role:editor on team:sre (inherits to project:prod-k8s)",
  "roles": ["team_sre:editor"],
  "evaluated_at": "2026-03-19T14:00:00Z"
}
```

### 14.4 Audit Log API

| Method | Endpoint | Description | Required Role |
|--------|---------|-------------|--------------|
| GET | `/v1/audit-logs` | Search audit logs | Admin |
| GET | `/v1/audit-logs/{log_id}` | Get single audit entry | Admin |
| POST | `/v1/audit-logs/export` | Export audit logs | Admin |
| GET | `/v1/audit-logs/stats` | Audit log statistics | Admin |
| GET | `/v1/compliance/reports` | List compliance reports | Admin |
| POST | `/v1/compliance/reports/generate` | Generate compliance report | Admin |

### 14.5 API Key Management API

| Method | Endpoint | Description | Required Role |
|--------|---------|-------------|--------------|
| GET | `/v1/api-keys` | List API keys | Editor |
| POST | `/v1/api-keys` | Create API key | Editor |
| GET | `/v1/api-keys/{key_id}` | Get key details (no secret) | Editor |
| PATCH | `/v1/api-keys/{key_id}` | Update key metadata | Editor |
| DELETE | `/v1/api-keys/{key_id}` | Revoke key | Editor |
| POST | `/v1/api-keys/{key_id}/rotate` | Rotate key | Editor |
| GET | `/v1/api-keys/{key_id}/usage` | Get key usage stats | Editor |

---

## 15. Performance Requirements

| Operation | Target Latency | Throughput |
|-----------|---------------|-----------|
| JWT validation | < 1ms p99 | 100,000 req/sec per node |
| Permission check (cached) | < 5ms p99 | 50,000 req/sec per node |
| Permission check (uncached) | < 50ms p99 | 10,000 req/sec per node |
| RBAC policy evaluation | < 10ms p99 | 20,000 req/sec per node |
| API key validation | < 5ms p99 | 50,000 req/sec per node |
| Audit log write | < 10ms p99 (async) | 100,000 events/sec |
| Audit log search | < 2s p99 | 100 concurrent queries |
| PII scan (per log line) | < 1ms p99 | 500,000 lines/sec |
| SAML assertion validation | < 100ms p99 | 1,000 req/sec |
| OIDC token exchange | < 200ms p99 | 1,000 req/sec |
| User login (email/password) | < 500ms p99 | 500 req/sec |
| SCIM full sync (10K users) | < 5 min | 1 sync/hour |
| Tenant context injection | < 1ms p99 | 100,000 req/sec |

**Availability**: Auth service targets 99.99% uptime (< 52 min downtime/year). All other security services target 99.9%.

**Caching Strategy**:
- JWT public keys cached with 1-hour TTL (invalidated on rotation)
- RBAC policies cached per-user with 5-minute TTL (invalidated on role change)
- API key metadata cached with 1-minute TTL (invalidated on revoke)
- Tenant quotas cached with 5-minute TTL

---

## 16. Success Metrics

### 16.1 Security Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Cross-tenant data leakage incidents | 0 | Pen test results + automated tests |
| Mean time to detect (MTTD) security incidents | < 15 min | SIEM alert latency |
| Mean time to contain (MTTC) security incidents | < 1 hour | Incident response logs |
| Vulnerability remediation SLA compliance | > 95% | Ticket tracking |
| MFA adoption rate (where enforced) | 100% | Auth system metrics |
| API keys with expiry set | > 90% | Key management metrics |
| Audit log integrity check pass rate | 100% | Daily integrity verification |
| PII detection recall | > 95% | Labeled test dataset |
| PII detection precision | > 99% | Labeled test dataset |

### 16.2 Operational Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| SSO setup time | < 30 min | Customer onboarding funnel |
| Auth overhead (p99 latency added) | < 100ms | API gateway metrics |
| SCIM sync reliability | 99.9% | SCIM operation success rate |
| User provisioning latency (SCIM) | < 60 sec | SCIM event timestamps |
| Session revocation propagation | < 60 sec | Session invalidation latency |
| Compliance report generation time | < 5 min | Report generation metrics |

### 16.3 Business Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Enterprise deals blocked by missing security feature | 0 | Sales pipeline tracking |
| SOC 2 Type II certification | Within 6 months of GA | Audit timeline |
| Customer security questionnaire completion time | < 2 hours | Support ticket tracking |
| Security-related customer churn | 0% | Customer success metrics |

---

## 17. Risks & Mitigations

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|-----------|
| R1 | Cross-tenant data leakage due to query engine bug | Low | Critical | Defense-in-depth (query engine + row-level security + storage isolation); automated cross-tenant tests in CI/CD; regular pen testing |
| R2 | JWT signing key compromise | Low | Critical | Ed25519 keys stored in HSM/KMS; automatic key rotation every 90 days; key revocation propagation < 60s |
| R3 | SCIM sync failure causes ghost accounts | Medium | High | SCIM reconciliation job runs hourly; alerts on sync failure; manual deprovisioning fallback |
| R4 | PII detection false negatives (PII stored in clear) | Medium | High | Defense-in-depth: ingest-time scan + periodic re-scan of stored data; external PII audit quarterly |
| R5 | Audit log storage corruption | Low | Critical | Hash chain integrity verification; cross-region replication; daily integrity checks; immutable storage (S3 Object Lock) |
| R6 | SSO provider outage prevents user login | Medium | High | Fallback to email/password for break-glass access (Owner only, MFA required); SSO provider health monitoring |
| R7 | Rate limiting too aggressive causes customer impact | Medium | Medium | Graduated rate limiting with burst allowance; per-customer tuning; real-time rate limit dashboard |
| R8 | Compliance certification delays (SOC 2) | Medium | High | Start evidence collection at day 1; use automated compliance tools; engage auditor early |
| R9 | Customer-managed KMS key revocation causes data loss | Low | Critical | Document key revocation implications in onboarding; daily backup with RayOlly-managed keys (if customer opts in); key health monitoring |
| R10 | Insider threat (malicious employee) | Low | Critical | Least-privilege access for employees; break-glass access with dual approval; all employee actions logged in separate audit trail; background checks |
| R11 | Supply chain attack via compromised dependency | Medium | High | Dependency scanning in CI/CD; SBOM generation; signed container images; reproducible builds |
| R12 | Regulatory landscape changes require rapid compliance updates | Medium | Medium | Modular compliance framework; dedicated compliance engineering team; quarterly regulatory review |

---

## Appendix A: Compliance Checklist

### SOC 2 Type II Readiness Checklist

- [ ] Access control policies documented
- [ ] MFA enforced for all privileged accounts
- [ ] RBAC implemented and tested
- [ ] Audit logging enabled for all systems
- [ ] Encryption at rest for all data stores
- [ ] Encryption in transit for all communication
- [ ] Vulnerability scanning in CI/CD
- [ ] Annual penetration test completed
- [ ] Incident response plan documented and tested
- [ ] Change management process defined
- [ ] Backup and recovery procedures tested
- [ ] Employee security training completed
- [ ] Vendor risk assessments completed
- [ ] Business continuity plan documented

### HIPAA Readiness Checklist

- [ ] BAA template approved by legal
- [ ] PHI data flow mapped
- [ ] PHI access controls implemented
- [ ] PHI audit logging enabled
- [ ] PHI encryption verified (at rest + in transit)
- [ ] Minimum necessary access enforced
- [ ] Breach notification procedures documented
- [ ] Employee HIPAA training completed
- [ ] Risk assessment completed
- [ ] PHI disposal procedures verified

### GDPR Readiness Checklist

- [ ] DPA template approved by legal
- [ ] Data processing inventory completed
- [ ] DSAR API implemented and tested
- [ ] Right to erasure implemented and tested
- [ ] PII detection and redaction pipeline operational
- [ ] Consent management implemented
- [ ] Cross-border data transfer mechanisms in place (SCCs)
- [ ] DPO appointed (or determination documented)
- [ ] Privacy impact assessment completed
- [ ] Data breach notification procedures documented (72h)

---

## Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **BAA** | Business Associate Agreement — HIPAA requirement for vendors handling PHI |
| **CMK** | Customer-Managed Key — encryption key owned and controlled by the customer |
| **DPA** | Data Processing Agreement — GDPR requirement for data processors |
| **DSAR** | Data Subject Access Request — individual's right to access their data under GDPR |
| **FIDO2** | Fast Identity Online 2 — passwordless authentication standard (WebAuthn + CTAP) |
| **mTLS** | Mutual TLS — both client and server authenticate via certificates |
| **OIDC** | OpenID Connect — authentication layer on top of OAuth 2.0 |
| **PAN** | Primary Account Number — credit card number |
| **PHI** | Protected Health Information — health data protected under HIPAA |
| **PII** | Personally Identifiable Information |
| **RBAC** | Role-Based Access Control |
| **SAML** | Security Assertion Markup Language — XML-based SSO standard |
| **SCIM** | System for Cross-domain Identity Management — user provisioning standard |
| **SCC** | Standard Contractual Clauses — GDPR mechanism for cross-border data transfers |
| **SPIFFE** | Secure Production Identity Framework for Everyone — workload identity standard |
| **TOTP** | Time-based One-Time Password (RFC 6238) |
| **WAF** | Web Application Firewall |
| **WORM** | Write Once, Read Many — immutable storage model |
