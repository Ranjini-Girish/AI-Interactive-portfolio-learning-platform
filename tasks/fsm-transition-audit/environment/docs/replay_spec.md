# FSM transition replay

Workflow logs record state-machine transitions for pull requests, deployments, and incidents. Each workflow references an FSM definition that declares allowed edges and terminal states.

Replay sorts and deduplicates transitions, validates state progression against the FSM, and emits findings for consistency violations. Dwell-time and integrity-hash rules are defined in `instruction.md`.
