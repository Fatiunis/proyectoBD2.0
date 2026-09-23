-- Crea una oferta relámpago: cupo, límite, precio e id, todo o nada.
--
-- KEYS[1] = oferta:{pid}:stock
-- KEYS[2] = oferta:{pid}:limite
-- KEYS[3] = oferta:{pid}:precio
-- KEYS[4] = oferta:{pid}:id
-- ARGV[1] = cantidad límite
-- ARGV[2] = precio de oferta (string con 2 decimales)
-- ARGV[3] = duración en segundos (TTL de las cuatro keys)
-- ARGV[4] = id único de esta oferta
--
-- Retorna 1 si la creó, 0 si ya había una oferta activa.
--
-- Al ser un único script, no puede quedar una oferta a medias (p. ej. cupo
-- sin precio) ni dos creaciones simultáneas pueden pisarse. El id distingue
-- esta oferta de una anterior del mismo producto cuyas reservas todavía
-- estén vivas (una reserva se respeta hasta 1 minuto después de que termine
-- la ventana): esas reservas no cuentan ni descuentan del cupo nuevo.
if redis.call('EXISTS', KEYS[1]) == 1 then
  return 0
end
local segundos = tonumber(ARGV[3])
redis.call('SET', KEYS[1], ARGV[1], 'EX', segundos)
redis.call('SET', KEYS[2], ARGV[1], 'EX', segundos)
redis.call('SET', KEYS[3], ARGV[2], 'EX', segundos)
redis.call('SET', KEYS[4], ARGV[4], 'EX', segundos)
return 1
