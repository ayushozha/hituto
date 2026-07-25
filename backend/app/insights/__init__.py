"""Optional personal-learning insight agent.

The durable evidence and deterministic fallback live in the service layer. This
package only turns an already-aggregated, content-minimized context into prose.
"""

from .agent import generate_report

__all__ = ["generate_report"]
