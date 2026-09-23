-- Quita la línea de oferta del carrito y libera la reserva en el acto.
--
-- KEYS[1] = oferta:{pid}:reservas
-- KEYS[2] = carrito:{id_usuario}
-- ARGV[1] = id_usuario
-- ARGV[2] = campo de la línea en el carrito ("oferta:{pid}")
--
-- Retorna 1 si liberó una reserva, 0 si no había nada que liberar.
-- Como la reserva nunca descontó el cupo (solo lo aparta), liberar es
-- simplemente borrar la entrada: las unidades vuelven a estar disponibles.
-- Una reserva "en_pago" NO se toca: hay un checkout en curso que la consumió
-- y que es quien decide si se confirma o se compensa.
redis.call('HDEL', KEYS[2], ARGV[2])

local crudo = redis.call('HGET', KEYS[1], ARGV[1])
if not crudo then
  return 0
end
local r = cjson.decode(crudo)
if r.e == 'activa' then
  redis.call('HDEL', KEYS[1], ARGV[1])
  return 1
end
return 0
