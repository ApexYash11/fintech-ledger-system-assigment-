"""Service layer — contains all business logic.

Services orchestrate operations across multiple repositories,
enforce business rules, and manage transactions.

Services are framework-agnostic (no FastAPI imports).
They receive dependencies via constructor injection.
"""
