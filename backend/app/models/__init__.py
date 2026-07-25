"""SQLAlchemy models package.

Re-exports every mapper so `from app.models import Course` keeps working, and importing
the package registers all mappers on `Base.metadata` (used by `init_db()` and Alembic).
"""
from .base import Base
from .billing import CreditEvent
from .course import (
    Artifact,
    Citation,
    CodingLabSession,
    Course,
    GenerationRun,
    Lesson,
    WhiteboardSession,
)
from .insight import InsightPreference, InsightSnapshot, LearningEvent
from .profile import LearnerProfile
from .source import CourseSource, LessonSourcePack, SourceChunk, SourceDocument

__all__ = [
    "Base",
    "CreditEvent",
    "Course",
    "Lesson",
    "Artifact",
    "Citation",
    "GenerationRun",
    "WhiteboardSession",
    "CodingLabSession",
    "LearningEvent",
    "InsightSnapshot",
    "InsightPreference",
    "LearnerProfile",
    "SourceDocument",
    "SourceChunk",
    "CourseSource",
    "LessonSourcePack",
]
