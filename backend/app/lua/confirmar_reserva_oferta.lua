-- Cierra una reserva consumida cuando el checkout ya se confirmó en Postgres.
-- Sus unidades ya se descontaron del cupo al consumirla: a partir de aquí
-- cuentan como vendidas (limite - cupo_sin_vender - unidades_en_pago).
--
-- KEYS[1] = oferta:{pid}:reservas
-- ARGV[1] = id_usuario
-- ARGV[2] = id de la oferta de la reserva consumida
--
-- Solo borra la entrada si sigue "en_pago" de esa oferta, para no borrar por
-- error una reserva nueva del mismo usuario.
local crudo = redis.call('HGET', KEYS[1], ARGV[1])
if not crudo then
  return 0
end
local r = cjson.decode(crudo)
if r.e == 'en_pago' and r.o == ARGV[2] then
  redis.call('HDEL', KEYS[1], ARGV[1])
  return 1
end
return 0
