-- Consume una reserva al iniciar el checkout: la pasa a "en_pago" y
-- descuenta sus unidades del cupo sin vender, en una sola operación atómica.
--
-- KEYS[1] = oferta:{pid}:stock
-- KEYS[2] = oferta:{pid}:id
-- KEYS[3] = oferta:{pid}:reservas
-- ARGV[1] = id_usuario
-- ARGV[2] = margen máximo del estado "en_pago" en ms
--
-- Retorna:
--   {1, cantidad, precio, vence_ms, id_oferta, descontado(1|0)}
--   {-1} si la reserva no existe o ya venció (se purga)
--   {-2} si la reserva ya está "en_pago" (otro checkout en curso)
--
-- Invariante que evita la sobreventa: para la oferta vigente,
--   cupo_sin_vender >= suma(reservas activas).
-- reservar_oferta.lua solo crea una reserva si cabe; aquí se resta del cupo
-- exactamente lo que se quita de "activas", así que el cupo nunca baja de 0.
--
-- Si la ventana de la oferta ya terminó (la key de stock expiró) la reserva
-- se respeta igual -- precio y cantidad viajan en la reserva -- y no se
-- descuenta nada (descontado = 0): no hay cupo que proteger. Tampoco se
-- descuenta si el cupo es de una oferta NUEVA del mismo producto (id distinto).
local t = redis.call('TIME')
local ahora = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

local crudo = redis.call('HGET', KEYS[3], ARGV[1])
if not crudo then
  return {-1}
end
local r = cjson.decode(crudo)
if r.e == 'en_pago' then
  if (r.l or 0) <= ahora then
    redis.call('HDEL', KEYS[3], ARGV[1])
    return {-1}
  end
  return {-2}
end
if r.v <= ahora then
  redis.call('HDEL', KEYS[3], ARGV[1])
  return {-1}
end

local margen = tonumber(ARGV[2])
r.e = 'en_pago'
r.l = ahora + margen
redis.call('HSET', KEYS[3], ARGV[1], cjson.encode(r))
if redis.call('PTTL', KEYS[3]) < margen then
  redis.call('PEXPIRE', KEYS[3], margen)
end

local descontado = 0
local id_actual = redis.call('GET', KEYS[2]) or ''
if redis.call('EXISTS', KEYS[1]) == 1 and id_actual == r.o then
  redis.call('DECRBY', KEYS[1], r.c)
  descontado = 1
end

return {1, r.c, r.p, r.v, r.o, descontado}
