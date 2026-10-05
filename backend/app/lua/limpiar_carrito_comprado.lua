-- Quita del carrito las líneas que se pagaron en un checkout ya confirmado.
--
-- KEYS[1] = carrito:{id_usuario}
-- ARGV    = pares campo, valor_json (tal como estaban al leer el carrito en
--           el checkout)
--
-- Solo borra una línea si su valor sigue IGUAL al que se pagó: si el comprador
-- cambió la cantidad o volvió a agregar el producto después de pagar, esa
-- línea nueva no se toca. Repetirlo es inofensivo (idempotente): una línea que
-- ya no está, o que cambió, simplemente se salta.
--
-- Retorna cuántas líneas borró.
local borradas = 0
for i = 1, #ARGV, 2 do
  if redis.call('HGET', KEYS[1], ARGV[i]) == ARGV[i + 1] then
    redis.call('HDEL', KEYS[1], ARGV[i])
    borradas = borradas + 1
  end
end
return borradas
