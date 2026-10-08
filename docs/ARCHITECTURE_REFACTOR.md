# MIE — arquitetura operacional após refatoração

AISStream.io
    │
    │ WebSocket + ping/pong + reconnect/backoff
    ▼
AISBackgroundService
    │ bounded Queue[AISObservation]
    ├──────────────► connection/data telemetry
    │
    ▼
Streamlit fragment / refresh
    │
    ├── ObservationStore
    ├── batch persistence
    │       └── PostgreSQL COPY → staging → INSERT ... ON CONFLICT DO NOTHING
    │
    ├── classical analytics — somente janela live
    └── temporal analytics — histórico real + sessão corrente
            ├── stitching < 5 min
            ├── fixed-grid resampling
            ├── observation mask
            └── TCN masked loss / inference

## Contratos de status

connection_status: CONNECTING | LIVE | STALE | CLOSED | ERROR

data_status: LIVE | STALE | NO_DATA

Isso elimina a ambiguidade entre LIVE AIS e WebSocket fechado. Uma janela
encerrada pode ter connection_status=CLOSED e data_status=LIVE se uma
mensagem válida foi recebida recentemente.

## Integração

1. Configure AISSTREAM_API_KEY.
2. Habilite opcionalmente DATABASE_URL + HISTORICAL_PERSISTENCE_ENABLED=true.
3. Opcionalmente defina HISTORICAL_RETENTION_DAYS entre 7 e 30.
4. Abra o Streamlit e use Start Live AIS · 2 Regions.
5. O WebSocket passa a rodar em daemon thread.
6. A UI drena a fila em lotes de aproximadamente 45 s e executa a análise fora
   do caminho de conexão.
7. Para uma validação longa, mantenha a página aberta e acompanhe connection,
   data status, WS, messages, active, queue, latency, gaps e cobertura temporal.

## Score temporal

deep_anomaly_score continua sendo um ranking de reconstrução. O módulo
src/ml/temporal/calibration.py fornece percentil empírico e o contrato de
alerta: percentil >= 99, score acima do baseline histórico e persistência em
pelo menos 3 janelas.

A calibração deve ser alimentada por scores históricos persistidos antes de
ser tratada como um alerta operacional de produção.

## Particionamento

A tabela atual já possui o índice operacional (mmsi, received_at). A partição
declarativa por data não é aplicada automaticamente nesta refatoração: uma
tabela regular exige uma migração de armazenamento para virar particionada.
Ela deve ser tratada quando o volume justificar, com planejamento das
partições e migração dos dados existentes.
