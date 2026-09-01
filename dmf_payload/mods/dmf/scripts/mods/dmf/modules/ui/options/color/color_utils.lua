local ColorUtils = {}

ColorUtils.normalize = function (color)
  if type(color) == "userdata" and Script.type_name(color) == "Vector4" then
    return {
      Quaternion.to_elements(color),
    }
  end

  return color
end

ColorUtils.copy = function (color)
  color = ColorUtils.normalize(color)

  return {
    color[1],
    color[2],
    color[3],
    color[4],
  }
end

ColorUtils.equal = function (first, second)
  first = ColorUtils.normalize(first)
  second = ColorUtils.normalize(second)

  return first[1] == second[1]
    and first[2] == second[2]
    and first[3] == second[3]
    and first[4] == second[4]
end

ColorUtils.clamp_integer = function (value, min_value, max_value)
  return math.round(math.clamp(value, min_value, max_value))
end

ColorUtils.hsv_to_rgb = function (hue, saturation, value)
  hue = hue % 360

  local chroma = value * saturation
  local hue_segment = hue / 60
  local second = chroma * (1 - math.abs(hue_segment % 2 - 1))
  local red, green, blue = 0, 0, 0

  if hue_segment < 1 then
    red, green = chroma, second
  elseif hue_segment < 2 then
    red, green = second, chroma
  elseif hue_segment < 3 then
    green, blue = chroma, second
  elseif hue_segment < 4 then
    green, blue = second, chroma
  elseif hue_segment < 5 then
    red, blue = second, chroma
  else
    red, blue = chroma, second
  end

  local match = value - chroma
  local clamp_integer = ColorUtils.clamp_integer

  return clamp_integer((red + match) * 255, 0, 255),
    clamp_integer((green + match) * 255, 0, 255),
    clamp_integer((blue + match) * 255, 0, 255)
end

ColorUtils.rgb_to_hsv = function (red, green, blue)
  red = red / 255
  green = green / 255
  blue = blue / 255

  local max_value = math.max(red, green, blue)
  local min_value = math.min(red, green, blue)
  local delta = max_value - min_value
  local hue = 0

  if delta ~= 0 then
    if max_value == red then
      hue = 60 * ((green - blue) / delta % 6)
    elseif max_value == green then
      hue = 60 * ((blue - red) / delta + 2)
    else
      hue = 60 * ((red - green) / delta + 4)
    end
  end

  local saturation = max_value == 0 and 0 or delta / max_value

  return hue, saturation, max_value
end

return ColorUtils
