# Environmental Intelligence Layer — Fase 1

Esta fase fornece apenas infraestrutura de alinhamento espacial-temporal:

```text
EnvironmentalProvider
        ↓
EnvironmentalDataset
        ↓
SpatialTemporalAligner
        ↓
VesselEnvironmentTrack
```

A camada é separada de `AISProvider` e não altera `AISObservation`, a semântica E1 ou o `VesselSnapshot`.

## Implementado

- `EnvironmentalNature.ENVIRONMENTAL_OBSERVATION`;
- `EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE`;
- `EnvironmentalPoint` imutável, com timestamps UTC, variáveis, resolução, metadata e provenance;
- `EnvironmentalDataset` provider-neutral, sem assumir sensor, série ou grid;
- protocolo `EnvironmentalProvider`, sem integração externa;
- `AlignmentPolicy` sem thresholds padrão;
- `SpatialTemporalAligner` para um ponto explícito, com distância e delta preservados;
- `VesselEnvironmentTrack` separado do AIS original;
- estados `NOT_ANALYZED` com reason codes para insuficiência;
- matching direto somente quando método e limites são fornecidos explicitamente.

## Match não é evidence

`SpatialTemporalMatch` representa somente um pareamento técnico espacial-temporal segundo a política configurada. Mesmo quando os status espacial e temporal são válidos, o objeto não constitui finding, sinal ambiental, influência ambiental, correlação ou causalidade. `EvidenceStatus` permanece separado e esta fase não promove um match válido a `ANALYZED_SIGNAL`.

## Limites deliberados

- Open-Meteo, NDBC/ERDDAP, Copernicus Marine e satélite não são implementados;
- não há nearest-cell, seleção implícita entre múltiplos pontos ou interpolação;
- nenhum threshold científico é escolhido por default;
- um estado de modelo usa `model_validity_time` como referência temporal canônica exposta também em `reference_time`, recebe status `LIMITED` e não é uma observação física;
- `AISObservation.received_at` continua sendo o instante de recebimento pelo MIE;
- `ais_timestamp_second` não é convertido em timestamp absoluto;
- não há correlação, causalidade, lag analysis, p-value ou finding ambiental;
- ausência de ambiente nunca vira `ANALYZED_NO_SIGNAL`.

## Decisões ainda requeridas

- threshold espacial;
- threshold temporal;
- política de interpolação;
- número mínimo de pares;
- persistência ambiental.

Todas permanecem como decisões explícitas do chamador ou `DESIGN_DECISION_REQUIRED`.
