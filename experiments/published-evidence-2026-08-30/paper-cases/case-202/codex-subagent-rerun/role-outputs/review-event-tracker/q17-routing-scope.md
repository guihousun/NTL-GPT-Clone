# Q17 Event Tracker routing scope — SDGSAT-1 classification

> Codex-subagent simulation. This is a routing review only; it is not a new Q17 execution and not a benchmark evaluation.

## Routing verdict

**`conditional_skip_supported`** for the current Q17 request.

The supplied Q17 materials describe a sensor/classification task: verify a real
preprocessed SDGSAT-1 RGB scene, compute `RRLI = R/G` and `RBLI = B/G`, then
apply the fixed Jia et al. (2024) ordered thresholds (`RRLI > 9` → RLED;
otherwise `RBLI > 0.57` → WLED; otherwise Other). The observation package hands
the indices from the NTL Data Specialist to the NTL Analyst. It contains no
event identity, event source, event time, local-time conversion, event window,
or event-to-observation attribution request.

Therefore an NTL Event Tracker call is not required for this scoped request.
The existing Q17 evidence route is consistent with Data Specialist → Analyst
processing (with Engineer checks), and the reviewed Q17 directory contains no
Event Tracker artifact or event-context handoff. This review does **not** invent
one and does not claim that Event Tracker executed.

## What remains supported

- The Q17 request is about SDGSAT-1 sensor-derived light-type classification,
  not an event timeline.
- The formal Q17 package reports 9,784,136 valid index pixels and a locked
  classification result; the post-lock comparison is implementation
  consistency, not ground-truth accuracy.
- The classification itself remains outside Event Tracker scope. Large ratios
  caused by small green denominators, accepted preprocessing, mixed-light
  uncertainty, and the lack of field labels remain Analyst limitations.

## Re-route condition

Call Event Tracker only if the Q17 task is expanded to require a source-bounded
event context, event date/time semantics, a temporal observation window, or an
event-linked interpretation. Even then, Event Tracker should supply context and
provenance only; it must not be used to fabricate a causal explanation for a
sensor classification map.

## Read evidence

The full path/byte/SHA-256 inventory is in the sibling `artifact-manifest.json`.
Key Q17 evidence hashes are:

- `formal-observation-package.json`: `ae36cc77d17dcb99900596c1ebd54dc10cb8685388bb8b949b39b3e5c51def09`
- `formal-data-specialist-log.md`: `851cdf92d55114f2894a3ceddb87e735470d636296c8119aad59ff3e666df136`
- `formal-analyst-log.md`: `34b834c0cdda46fbb1fab3df1f56bf8f639dd9979910b0d0c140b80decfc492d`
- `evidence-report.json`: `0fd4261070a44f4f973d0c0e6de1fecac21b6aceb1a2c32ad45cbfc2a712e6c2`
