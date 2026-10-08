# Investigação operacional de MMSIs

As consultas abaixo usam somente observações AIS reais persistidas.

## Top MMSIs por velocidade média

```sql
SELECT mmsi,
       COUNT(*) AS reports,
       ROUND(AVG(sog_knots)::numeric, 2) AS avg_sog_knots,
       MAX(sog_knots) AS max_sog_knots
FROM ais_observations
WHERE valid = TRUE
  AND received_at >= NOW() - INTERVAL '30 days'
GROUP BY mmsi
HAVING COUNT(*) >= 10
ORDER BY avg_sog_knots DESC
LIMIT 50;
```

## Gaps longos por MMSI

```sql
WITH ordered AS (
    SELECT mmsi, received_at,
           LAG(received_at) OVER (PARTITION BY mmsi ORDER BY received_at) AS previous_at
    FROM ais_observations
    WHERE valid = TRUE
      AND received_at >= NOW() - INTERVAL '30 days'
)
SELECT mmsi,
       previous_at,
       received_at,
       EXTRACT(EPOCH FROM (received_at - previous_at)) AS gap_seconds
FROM ordered
WHERE previous_at IS NOT NULL
  AND received_at - previous_at > INTERVAL '15 minutes'
ORDER BY gap_seconds DESC
LIMIT 100;
```

## Mudanças bruscas de posição

```sql
WITH ordered AS (
    SELECT mmsi, received_at, geom, sog_knots,
           LAG(received_at) OVER (PARTITION BY mmsi ORDER BY received_at) AS previous_at,
           LAG(geom) OVER (PARTITION BY mmsi ORDER BY received_at) AS previous_geom
    FROM ais_observations
    WHERE valid = TRUE
)
SELECT mmsi,
       received_at,
       EXTRACT(EPOCH FROM (received_at - previous_at)) AS dt_seconds,
       ST_Distance(
           geom::geography,
           previous_geom::geography
       ) AS distance_m
FROM ordered
WHERE previous_at IS NOT NULL
  AND previous_geom IS NOT NULL
  AND received_at - previous_at <= INTERVAL '5 minutes'
ORDER BY distance_m DESC
LIMIT 100;
```

## Loitering

Use uma janela móvel por MMSI para detectar baixa velocidade com grande permanência espacial:

- SOG persistentemente baixa;
- deslocamento acumulado pequeno;
- duração acima do limiar operacional;
- concentração espacial em raio reduzido.

## Spoofing / comportamento inconsistente

Priorizar:

1. saltos espaciais incompatíveis com o intervalo de recepção;
2. SOG reportado muito diferente da velocidade derivada;
3. COG/heading incompatíveis com a trajetória;
4. gaps repetitivos e sincronizados;
5. mudanças abruptas de posição que reaparecem em outra área;
6. persistência do padrão por múltiplas janelas.

A investigação deve combinar evidência temporal, espacial e de qualidade; um único score não deve ser tratado como prova de spoofing.
