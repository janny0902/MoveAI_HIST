# Windows용: db-dumps/moveaidb.dump → mvp-moveai-db 복원
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Dump = if ($args[0]) { $args[0] } else { Join-Path $Root 'db-dumps\moveaidb.dump' }
if (-not (Test-Path $Dump)) { throw "dump 없음: $Dump" }

docker cp $Dump mvp-moveai-db:/tmp/moveaidb.dump
docker exec mvp-moveai-db psql -U moveaiuser -d moveaidb -v ON_ERROR_STOP=1 `
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO moveaiuser; GRANT ALL ON SCHEMA public TO public;"
docker exec mvp-moveai-db pg_restore -U moveaiuser -d moveaidb --no-owner --role=moveaiuser /tmp/moveaidb.dump
Write-Host '[restore] OK'
docker exec mvp-moveai-db psql -U moveaiuser -d moveaidb -c `
  "SELECT 'volumetric_cargo' t, COUNT(*) c FROM volumetric_cargo UNION ALL SELECT 'trucks', COUNT(*) FROM trucks UNION ALL SELECT 'cargo_requests', COUNT(*) FROM cargo_requests;"
docker compose -f (Join-Path $Root 'docker-compose.yml') restart backend-spring
