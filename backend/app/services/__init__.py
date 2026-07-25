"""Service layer: business logic and DB orchestration, kept out of the API handlers.

Route handlers (app/api/v1/) own HTTP concerns — path/dep parsing, ownership/404
checks, status codes, response models — and delegate the actual work here.
"""
