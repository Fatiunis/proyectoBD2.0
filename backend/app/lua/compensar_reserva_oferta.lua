-- Compensa un consumo cuando el checkout falla después de consumir la reserva.
--
-- KEYS[1] = oferta:{pid}:stock
-- KEYS[2] = oferta:{pid}:id
-- KEYS[3] = oferta:{pid}:reservas
-- ARGV[1] = id_usuario
-- ARGV[2] = cantidad consumida
-- ARGV[3] = id de la oferta a la que pertenecía la reserva
-- ARGV[4] = 1 si el consumo descontó del cupo, 0 si no
--
-- Retorna 1 si la reserva volvió a "activa", 0 si no se restauró.
--
-- 1. Devuelve las unidades al cupo solo si se habían descontado y la MISMA
--    oferta sigue viva (si expiró o la reemplazó otra, no hay a dónde volver;
--    INCRBY sobre una key inexistente además la crearía sin TTL).
-- 2. Restaura la reserva con su vencimiento ORIGINAL si todavía no pasó y la
--    entrada sigue "en_pago" de esa oferta (si alguien finalizó la oferta, el
--    hash ya no la tiene y no se resucita). Si ya venció, se borra.
local t = redis.call('TIME')
local ahora = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

local cantidad = tonumber(ARGV[2])
local id_oferta = ARGV[3]

if ARGV[4] == '1' and redis.call('EXISTS', KEYS[1]) == 1
    and (redis.call('GET', KEYS[2]) or '') == id_oferta then
  redis.call('INCRBY', KEYS[1], cantidad)
end

local crudo = redis.call('HGET', KEYS[3], ARGV[1])
if not crudo then
  return 0
end
local r = cjson.decode(crudo)
if r.e ~= 'en_pago' or r.o ~= id_oferta then
  return 0
end
if r.v <= ahora then
  redis.call('HDEL', KEYS[3], ARGV[1])
  return 0
end

r.e = 'activa'
r.l = nil
redis.call('HSET', KEYS[3], ARGV[1], cjson.encode(r))
local restante = r.v - ahora
if redis.call('PTTL', KEYS[3]) < restante then
  redis.call('PEXPIRE', KEYS[3], restante)
end
return 1
