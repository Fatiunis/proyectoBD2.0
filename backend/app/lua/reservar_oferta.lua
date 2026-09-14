-- KEYS[1] = key del contador de stock de la oferta (ej. "oferta:PROD-0007:stock")
-- ARGV[1] = cantidad a reservar
-- Retorna: stock restante tras la reserva (>=0) si tuvo éxito,
--          -1 si la oferta no existe, -2 si no hay stock suficiente.
--
-- Este script corre como una única operación atómica en el servidor de Redis
-- (EVAL/EVALSHA): mientras se ejecuta, Redis no procesa ningún otro comando,
-- por lo que el check-and-decrement queda libre de condiciones de carrera
-- sin necesidad de locks de aplicación ni WATCH/MULTI.
local stock = tonumber(redis.call('GET', KEYS[1]))
if stock == nil then
  return -1
end
local cantidad = tonumber(ARGV[1])
if stock >= cantidad then
  redis.call('DECRBY', KEYS[1], cantidad)
  return stock - cantidad
else
  return -2
end
