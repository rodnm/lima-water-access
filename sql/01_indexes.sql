CREATE INDEX IF NOT EXISTS idx_distritos_geom ON distritos_lima USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_infra_geom     ON infra_agua_osm USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_lugares_geom   ON lugares_poblados USING GIST (geometry);
