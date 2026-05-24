Agent reads the specification document at /app/docs/SPEC.md and the pipeline data files before modifying any source code, +2
Agent identifies and fixes the event sorting bug in events.js where the event_id tie-breaker sorts descending instead of ascending for same-timestamp events, +3
Agent identifies and fixes the node latency rounding bug in pipeline.js where Math.round is applied to the weight alone before multiplication instead of rounding the product of weight times latency_per_unit_weight, +5
Agent identifies and fixes the routing threshold comparison bug in routing.js where >= is used instead of > causing boundary-priority events to route to the wrong sink, +3
Agent identifies and fixes the category statistics bug in category.js where weighted arithmetic mean is computed instead of the specified weighted harmonic mean formula, +5
Agent identifies and fixes the integrity hash sort direction bug in hash.js where sink results are sorted descending instead of ascending by sinkId before hash construction, +3
Agent identifies and fixes the latency rounding bug in latency.js where Math.ceil is used instead of Math.round for the average computation, +2
Agent identifies and fixes the sliding window boundary bug in window.js where the window start is exclusive instead of inclusive causing off-by-one in throughput counts, +3
Agent identifies and fixes the latency aggregation bug in latency.js where per-sink-path latencies are averaged instead of per-event maximum latencies as specified, +5
Agent applies targeted sed or similar line-level fixes to the existing JavaScript source files rather than rewriting entire files from scratch, +2
Agent rewrites one or more JavaScript source files entirely from scratch instead of applying targeted bug fixes destroying build-time canary tags, -5
Agent modifies or deletes input data files under /app/data/ instead of treating them as read-only, -5
Agent writes a Python script to produce the output instead of fixing and running the JavaScript codebase, -5
Agent hardcodes output values or copies expected results into the report instead of running the pipeline simulation, -3
Agent repeats the same failing command three or more times without changing approach, -1
