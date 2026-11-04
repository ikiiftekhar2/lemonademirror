-- every 5 s: frames shown since last tick, drops
local last_n, last_t = nil, nil
mp.add_periodic_timer(5, function()
  local n = mp.get_property_number("estimated-frame-number") or 0
  local t = mp.get_time()
  if last_n then
    mp.msg.warn(string.format("FPS %.1f  dropped(vo)=%s dropped(dec)=%s", (n-last_n)/(t-last_t),
      mp.get_property("frame-drop-count"), mp.get_property("decoder-frame-drop-count")))
  end
  last_n, last_t = n, t
end)
