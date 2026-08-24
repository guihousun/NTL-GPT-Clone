# GEE NTL Date & Boundary Handling — Case 201 version record

## Runtime inspection

The current runtime Skill already contains the required conceptual chain:
event time, UTC/local distinction, first-night logic, UTC-indexed file-date
mapping, end-exclusive date queries, and an ambiguity/no-data guard. Its
content is frozen for this case by the SHA-256 in
`gee-ntl-date-boundary-handling.version.json`.

## Case 201 implementation addition

No runtime Skill file is overwritten. This package supplies an executable,
generic companion implementation in
`../implementation/gee_ntl_date_boundary_handling.py` plus unit tests. The
addition makes two rules machine-testable for the paper case:

1. An event after the local candidate acquisition window maps to the next
   local-night label.
2. A UTC-indexed product-date eligibility failure is terminal for the first
   night; a later date cannot be substituted silently.

## Runtime scope disclosure

The historical root checkout references this Skill from an Engineer prompt, but
this Case 201 run does not invoke a deployed runtime graph. The testable
implementation and its role outputs are evidence of a Codex-subagent workflow
simulation only.
