# Deploy no Streamlit Community Cloud

Este documento descreve o procedimento final para o proprietário do repositório. O código já está preparado para iniciar sem credencial, mas esse estado serve apenas para mostrar a indisponibilidade de dados. O sistema só pode ser considerado operacional quando o app publicado receber mensagens reais do AISStream.

## 1. Criar o app

No [Streamlit Community Cloud](https://share.streamlit.io/), selecione **Create app**, escolha o repositório `edu-moraess/maritime-intelligence-engine`, branch `main` e informe `app.py` como arquivo principal. Mantenha o repositório privado ou ajuste a visibilidade conforme a política da sua conta.

## 2. Configurar Secrets

Em **App settings → Secrets**, adicione os valores reais do ambiente operacional. O segredo não deve ser commitado no GitHub.

```toml
AISSTREAM_API_KEY = "<chave-real-do-AISStream>"
AIS_AREA_MIN_LAT = "25.603"
AIS_AREA_MIN_LON = "-80.208"
AIS_AREA_MAX_LAT = "25.835"
AIS_AREA_MAX_LON = "-79.879"
AIS_COLLECTION_SECONDS = "60"
AIS_MAX_MESSAGES = "3000"
AIS_MAX_VESSELS = "1000"
AIS_STALE_AFTER_SECONDS = "180"
AIS_PROVIDER = "aisstream"
# Optional external PostgreSQL/PostGIS. Omit for LIVE-ONLY.
# DATABASE_URL = "<external-postgresql-url>"
# Explicit opt-in; DATABASE_URL alone never enables historical INSERTs.
HISTORICAL_PERSISTENCE_ENABLED = "false"
```

A chave deve vir da conta oficial do AISStream. Não use credenciais de exemplo, valores inventados ou uma chave inserida no código. O aplicativo lê `st.secrets["AISSTREAM_API_KEY"]` no lado do servidor e nunca abre uma conexão AISStream diretamente no navegador. `DATABASE_URL` é opcional e deve apontar para um PostgreSQL/PostGIS externo; nunca configure PostgreSQL local no Streamlit Cloud. Sem essa variável, o app deve declarar `HISTORICAL DATABASE NOT CONFIGURED` e permanecer LIVE-ONLY. Mesmo com ela, a persistência fica desligada por padrão; somente `HISTORICAL_PERSISTENCE_ENABLED = "true"` ou o controle equivalente da sidebar permite gravação. Com ambos, a primeira coleta real aplica as migrations versionadas e o writer persiste somente observações válidas, sem substituir o estado live.

## 3. Verificação pós-deploy

Abra o app publicado e confirme, nesta ordem:

| Verificação | Evidência esperada |
| --- | --- |
| Boot | O app abre sem erro fatal e mostra o shell MIE |
| Credencial | A sidebar mostra `CONFIGURED`, sem revelar o valor |
| Conexão | Ao clicar em `Collect real AIS`, o estado passa por `CONNECTING` |
| Dados | O estado passa para `LIVE AIS` somente após mensagens reais serem recebidas |
| Mensagens | O contador de mensagens cresce durante a janela de coleta |
| Mapa | Embarcações observadas aparecem no mapa com MMSI e telemetry reais |
| Páginas | Overview, Vessels, Vessel Intelligence, Trajectory Analysis, Behavior, Anomalies, Traffic, Data Quality e System carregam |
| Integridade | Nenhuma página mostra dados se a conexão estiver indisponível |
| Histórico | Sem `DATABASE_URL`, aparece `HISTORICAL DATABASE NOT CONFIGURED`; com URL e opt-in desligado, aparece `HISTORICAL PERSISTENCE OFF`; com banco indisponível, aparece `HISTORICAL DATABASE UNAVAILABLE` e o live continua |
| Segurança | A chave AIS e a URL do banco não aparecem na interface, logs, respostas ou código-fonte |

Se a conexão AIS falhar, o resultado esperado é `DISCONNECTED` ou `REAL AIS DATA UNAVAILABLE`, nunca uma coleção artificial de navios. Se o banco falhar, o resultado esperado é `HISTORICAL DATABASE UNAVAILABLE`, com a sessão live preservada em memória. Com DATABASE_URL sem opt-in, o resultado esperado é `HISTORICAL PERSISTENCE OFF` e nenhuma tentativa de conexão histórica. O AISStream documenta que o serviço é WebSocket-only, exige uma assinatura com bounding box e não oferece replay durável; por isso a verificação deve ser feita com mensagens recebidas naquele momento [1].

## 4. Critério de sucesso

Não declare o deploy como “LIVE” apenas porque a página abriu. O critério mínimo é: o app publicado mostra `LIVE AIS`, o contador `MESSAGES` é positivo e crescente, `LAST RECEIVED` é recente e os alvos do mapa correspondem às mensagens reais recebidas pelo processo Streamlit. O estado histórico deve ser reportado separadamente como `HISTORICAL DATABASE NOT CONFIGURED`, `HISTORICAL PERSISTENCE OFF`, `HISTORICAL DATABASE AVAILABLE` ou `HISTORICAL DATABASE UNAVAILABLE`; ele nunca deve ser inferido a partir do estado live.

## Referência

[1]: https://aisstream.io/documentation "AISStream — Developer Documentation"
