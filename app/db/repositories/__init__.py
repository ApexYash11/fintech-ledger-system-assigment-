"""Repository implementations.

Each repository provides a collection-oriented interface to its
database table, hiding SQLAlchemy details behind a thin abstraction.

This enables:
1. Unit testing services with mock repositories
2. Changing ORM implementation without affecting services
3. Centralising query logic (indexing, eager loading, etc.)
"""
