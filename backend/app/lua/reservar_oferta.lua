-- Reserva temporal de unidades de una oferta relámpago.
--
-- KEYS[1] = oferta:{pid}:stock     (cupo sin vender)
-- KEYS[2] = oferta:{pid}:precio    (precio de oferta, string "123.45")
-- KEYS[3] = oferta:{pid}:id        (identificador de esta oferta concreta)
-- KEYS[4] = oferta:{pid}:reservas  (hash id_usuario -> reserva JSON)
-- ARGV[1] = id_usuario
-- ARGV[2] = cantidad a reservar
-- ARGV[3] = duración de la reserva en milisegundos
--
-- Retorna:
--   {1, disponibles_tras_reservar, precio_oferta, ms_restantes_reserva}
--   {-1} si no hay oferta activa (sin stock o sin precio)
--   {-2} si no hay unidades suficientes (cupo sin vender - reservas activas)
--   {-3} si el usuario ya tiene una reserva en esta oferta
--
-- Formato de cada reserva (valor del hash, JSON):
--   c = cantidad, p = precio de oferta (string), v = vence (ms epoch),
--   e = "activa" | "en_pago", o = id de la oferta que la creó,
--   l = límite del estado "en_pago" (ms epoch; solo si e == "en_pago")
--
-- Todo (purga de vencidas, cálculo de disponibilidad y alta de la reserva)
-- corre dentro de UNA ejecución atómica del servidor Redis: ningún otro
-- comando se intercala, así que dos compradores no pueden ver el mismo
-- "disponible" y apartar ambos la última unidad. La hora sale de
-- redis.call('TIME') (reloj del servidor Redis), no del reloj de cada proceso
-- Flask, para que todas las instancias comparen contra el mismo reloj.

local t = redis.call('TIME')
local ahora = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

local stock = tonumber(redis.call('GET', KEYS[1]))
local precio = redis.call('GET', KEYS[2])
if stock == nil or not precio then
  return {-1}
end
local id_oferta = redis.call('GET', KEYS[3]) or ''

local id_usuario = ARGV[1]
local cantidad = tonumber(ARGV[2])
local reserva_ms = tonumber(ARGV[3])

-- Purga de reservas vencidas y suma de las activas de ESTA oferta. Las que
-- están "en_pago" ya se descontaron del cupo al consumirlas, no se suman.
local activas = 0
local entradas = redis.call('HGETALL', KEYS[4])
for i = 1, #entradas, 2 do
  local r = cjson.decode(entradas[i + 1])
  if (r.e == 'activa' and r.v <= ahora) or (r.e == 'en_pago' and (r.l or 0) <= ahora) then
    redis.call('HDEL', KEYS[4], entradas[i])
  elseif r.e == 'activa' and r.o == id_oferta then
    activas = activas + r.c
  end
end

if redis.call('HEXISTS', KEYS[4], id_usuario) == 1 then
  return {-3}
end

local disponibles = stock - activas
if disponibles < cantidad then
  return {-2}
end

local reserva = {c = cantidad, p = precio, v = ahora + reserva_ms, e = 'activa', o = id_oferta}
redis.call('HSET', KEYS[4], id_usuario, cjson.encode(reserva))

-- El hash de reservas vive lo que queda de la oferta más la duración de una
-- reserva (una reserva hecha en el último segundo se respeta completa).
local ttl_oferta = redis.call('PTTL', KEYS[1])
if ttl_oferta < 0 then ttl_oferta = 0 end
local ttl_necesario = ttl_oferta + reserva_ms
if redis.call('PTTL', KEYS[4]) < ttl_necesario then
  redis.call('PEXPIRE', KEYS[4], ttl_necesario)
end

return {1, disponibles - cantidad, precio, reserva_ms}
