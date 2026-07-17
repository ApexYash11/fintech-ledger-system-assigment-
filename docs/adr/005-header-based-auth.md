# ADR 005: Header-Based Authentication (Assignment Constraint)

**Status:** Accepted (temporary)  
**Context:** This is a take-home assignment; a full OAuth2/JWT implementation would shift focus from the fintech domain to auth plumbing.  
**Decision:** Use X-User-Id and X-Admin-Key headers for mock authentication.  
**Consequences:**
- + Fast to implement, zero setup
- + Focuses review on the financial domain, not auth
- − No real security: anyone can impersonate any user
- − Production replacement: OAuth2 with JWT, admin role in token claims
- − Migration path: add a real auth dependency, keep the current auth as a "mock mode" toggle for integration tests
