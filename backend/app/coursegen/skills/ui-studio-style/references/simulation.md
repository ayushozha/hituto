# Simulation mode

Use `simulation` when a bounded variable changes a dynamic system and observing that relationship
teaches the objective.

## Required learner loop

Change one input → run or step the model → watch the stage and readout change together → pause and
explain the cause/effect relationship.

## Required manifest behavior

- Declare `parameterize`, `playback`, and `reset` capabilities.
- Provide at least one bounded range control with units and a safe default.
- Provide play/pause behavior and a deterministic initial state.
- Synchronize the stage, current-value readout, and any chart.
- Use a sandbox-verified trace when factual numerical accuracy matters.

## Asset routing

Prefer procedural canvas/Three.js driven by known equations or supplied trace data. A static GLB may
provide visual context but must not become the simulation model. Do not claim physical accuracy
from decorative mesh motion.

## Interaction checks

- Each input produces an immediate visible change.
- Play, pause, and reset preserve deterministic state.
- Units, limits, and current values remain visible and keyboard-operable.
- Reduced motion supports stepping or a static state sequence.
- Readouts agree with the verified trace or deterministic model.
