-- Lectura consistente de una oferta (purga las reservas vencidas).
--
-- KEYS[1] = oferta:{pid}:stock
-- KEYS[2] = oferta:{pid}:limite
-- KEYS[3] = oferta:{pid}:precio
-- KEYS[4] = oferta:{pid}:id
-- KEYS[5] = oferta:{pid}:reservas
-- ARGV[1] = id_usuario a consultar ('' si no se pidió)
--
-- Retorna {-1} si no hay oferta activa, o bien
--   {1, cupo_sin_vender, limite|'', precio|'', ttl_ms, unidades_activas,
--    unidades_en_pago, u_cantidad|-1, u_precio|'', u_ms_restantes|-1}
-- (Lua no admite nil dentro de una tabla de respuesta: se usan centinelas.)
local t = redis.call('TIME')
local ahora = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

local stock = tonumber(redis.call('GET', KEYS[1]))
if stock == nil then
  return {-1}
end
local limite = redis.call('GET', KEYS[2]) or ''
local precio = redis.call('GET', KEYS[3]) or ''
local id_oferta = redis.call('GET', KEYS[4]) or ''
local ttl = redis.call('PTTL', KEYS[1])

local activas = 0
local en_pago = 0
local u_c, u_p, u_ms = -1, '', -1
local entradas = redis.call('HGETALL', KEYS[5])
for i = 1, #entradas, 2 do
  local r = cjson.decode(entradas[i + 1])
  if (r.e == 'activa' and r.v <= ahora) or (r.e == 'en_pago' and (r.l or 0) <= ahora) then
    redis.call('HDEL', KEYS[5], entradas[i])
  else
    if r.o == id_oferta then
      if r.e == 'activa' then activas = activas + r.c else en_pago = en_pago + r.c end
    end
    if entradas[i] == ARGV[1] and r.e == 'activa' then
      u_c, u_p, u_ms = r.c, r.p, r.v - ahora
    end
  end
end

return {1, stock, limite, precio, ttl, activas, en_pago, u_c, u_p, u_ms}
