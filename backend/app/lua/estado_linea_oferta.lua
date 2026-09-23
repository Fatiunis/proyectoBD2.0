-- Estado de la reserva detrás de una línea de oferta del carrito. Si la
-- reserva ya no existe o venció, quita la línea del carrito en la MISMA
-- operación atómica (así no se borra por error una línea recién creada por
-- una reserva nueva que se colara entre la lectura y el borrado).
--
-- KEYS[1] = oferta:{pid}:reservas
-- KEYS[2] = carrito:{id_usuario}
-- ARGV[1] = id_usuario
-- ARGV[2] = campo de la línea en el carrito ("oferta:{pid}")
--
-- Retorna {0} si la línea se quitó, o {1, estado, cantidad, precio, ms_restantes}.
local t = redis.call('TIME')
local ahora = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

local crudo = redis.call('HGET', KEYS[1], ARGV[1])
local r = nil
if crudo then
  r = cjson.decode(crudo)
  if (r.e == 'activa' and r.v <= ahora) or (r.e == 'en_pago' and (r.l or 0) <= ahora) then
    redis.call('HDEL', KEYS[1], ARGV[1])
    r = nil
  end
end

if r == nil then
  redis.call('HDEL', KEYS[2], ARGV[2])
  return {0}
end

local restantes = r.v - ahora
if restantes < 0 then restantes = 0 end
return {1, r.e, r.c, r.p, restantes}
