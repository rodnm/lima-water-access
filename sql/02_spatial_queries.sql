WITH
lugares_por_distrito AS (
    SELECT d."NAME_3" AS distrito, l.geometry AS lugar_geom
    FROM distritos_lima d
    JOIN lugares_poblados l ON ST_Within(l.geometry, d.geometry)
),
fallback AS (
    SELECT d."NAME_3" AS distrito, ST_Centroid(d.geometry) AS lugar_geom
    FROM distritos_lima d
    WHERE NOT EXISTS (
        SELECT 1 FROM lugares_poblados l WHERE ST_Within(l.geometry, d.geometry)
    )
),
todos AS (
    SELECT * FROM lugares_por_distrito
    UNION ALL
    SELECT * FROM fallback
),
dist AS (
    SELECT o.distrito, MIN(ST_Distance(o.lugar_geom, i.geometry)) AS dist_min
    FROM todos o
    CROSS JOIN infra_agua_osm i
    GROUP BY o.distrito, o.lugar_geom
)
SELECT
    distrito,
    ROUND(AVG(dist_min)::numeric, 1) AS dist_promedio_metros,
    ROUND(MIN(dist_min)::numeric, 1) AS dist_minima_metros,
    COUNT(*)                          AS n_lugares_medidos
FROM dist
GROUP BY distrito
ORDER BY dist_promedio_metros DESC;
