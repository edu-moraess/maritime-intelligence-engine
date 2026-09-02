# Validation Record — 2026-09-01

## Purpose

This record documents the live AIS evidence used to introduce adaptive temporal scale selection in the Maritime Intelligence Engine (MIE).

## Houston Ship Channel — live session

Observed session:

- Region: Houston Ship Channel
- Collection elapsed: 974.1 s
- Real AIS position reports observed: 549
- Persisted observations: 549
- Active vessels: 181
- AIS source: AISStream.io
- Historical persistence: enabled
- Temporal model: TCN Autoencoder
- Temporal training: 30 epochs
- Training time: 3.94 s
- Training loss: 0.525633
- Inference: available

### Temporal coverage

| Minimum real observations | Eligible tracks |
|---:|---:|
| ≥4 | 69 / 181 |
| ≥8 | 11 / 181 |
| ≥16 | 0 / 181 |
| ≥32 | 0 / 181 |

Window availability:

| Window | Sliding | Non-overlapping |
|---|---:|---:|
| T=8 | 17 | 11 |
| T=16 | 0 | 0 |
| T=32 | 0 | 0 |

Additional diagnostics:

- median points per track: 3
- median track duration: 7.0 min
- maximum receive-time gap: 24.7 min
- gaps above the configured diagnostic threshold: 3

## Danish Straits comparison

Two previous 900-second-class real AIS sessions showed materially denser temporal coverage:

- approximately 2.1k real AIS position reports per session;
- approximately 617–633 active vessels;
- 263 tracks with ≥4 points;
- TCN training available at T=32.

The comparison is descriptive. It is not a controlled benchmark and must not be interpreted as evidence that one region or one session is intrinsically better than another.

## Engineering conclusion

The evidence demonstrates that a fixed T=32 temporal sequence is not uniformly available across monitored regions and sessions.

PR #34 therefore introduces conservative adaptive selection:

`T=32 → T=16 → T=8 → NOT_READY`

The selector chooses the longest candidate scale for which the minimum required number of tracks contains that many validated real AIS observations.

No interpolation, synthetic observations, or temporal stretching is introduced.

For the Houston evidence above, the expected adaptive scale is **T=8** because 11 tracks contain at least 8 observations while fewer than 8 tracks contain 16 observations.

## Validation boundary

This evidence validates the existence and variability of real AIS temporal coverage. It does **not** validate:

- anomaly-score accuracy;
- calibrated probabilities;
- universal maritime behavior classification;
- causal explanations;
- malicious-intent detection;
- cross-region model generalization;
- superiority of TCN over Isolation Forest.

Those claims require controlled datasets, historical baselines, out-of-sample evaluation, and domain validation.

## Next gate

After PR #34 is merged and deployed:

1. verify that the live System page reports the selected adaptive scale;
2. verify Houston selects T=8 using the observed coverage;
3. verify denser regions retain T=16/T=32 when supported;
4. compare temporal coverage across the 30 region presets;
5. establish a quantitative temporal validation protocol before further model architecture changes.
