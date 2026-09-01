local dmf = get_mod("DMF")

local ColorPickerDefinitions = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/color/color_picker_definitions")
local ColorPickerGamepad = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/color/color_picker_gamepad")
local ColorUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/color/color_utils")
local TextInputUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/text_input_utils")

local PICKER_SIZE = ColorPickerDefinitions.picker_size
local clamp_integer = ColorUtils.clamp_integer
local colors_equal = ColorUtils.equal
local copy_color = ColorUtils.copy
local hsv_to_rgb = ColorUtils.hsv_to_rgb
local rgb_to_hsv = ColorUtils.rgb_to_hsv

local ViewElementColorPicker = class("ViewElementColorPicker", "ViewElementBase")

ViewElementColorPicker.init = function (self, parent, draw_layer, start_scale, context)
  local has_alpha = context.entry.has_alpha
  local color = ColorUtils.normalize(context.color)
  local definitions, field_names, gamepad_navigation_items = ColorPickerDefinitions.create(has_alpha)

  ViewElementColorPicker.super.init(self, parent, draw_layer, start_scale, definitions)

  self._entry = context.entry
  self._has_alpha = has_alpha
  self._field_names = field_names
  self._field_writing = {}
  self._draft_color = copy_color(color)

  local hue, saturation, value = rgb_to_hsv(color[2], color[3], color[4])

  self._hue = hue
  self._saturation = saturation
  self._value = value
  self._gamepad_using_cursor_navigation = Managers.ui:using_cursor_navigation()

  ColorPickerGamepad.init(self, gamepad_navigation_items)

  self._widgets_by_name.title.content.text = context.entry.display_name
    or Managers.localization:localize("loc_settings_option_unavailable")
  self._widgets_by_name.back_button.content.text = Localize("loc_view_back")

  for i = 1, #field_names do
    local field_name = field_names[i]
    local content = self._widgets_by_name["input_" .. field_name].content

    content.hotspot.use_is_focused = true
    content.close_on_backspace = false
    content.max_length = field_name == "hex" and 7 or 3
  end

  self._widgets_by_name.sv.content.on_pointer_changed = callback(self, "_on_sv_pointer_changed")
  self._widgets_by_name.hue.content.on_pointer_changed = callback(self, "_on_hue_pointer_changed")

  if has_alpha then
    self._widgets_by_name.alpha.content.on_pointer_changed = callback(self, "_on_alpha_pointer_changed")
  end

  self:_sync_widgets()
end

ViewElementColorPicker._set_input_text = function (self, field_name, value)
  local content = self._widgets_by_name["input_" .. field_name].content

  if not content.is_writing then
    content.input_text = value
  end
end

ViewElementColorPicker._sync_fields = function (self)
  local color = self._draft_color

  self:_set_input_text("r", string.format("%d", color[2]))
  self:_set_input_text("g", string.format("%d", color[3]))
  self:_set_input_text("b", string.format("%d", color[4]))
  self:_set_input_text("h", string.format("%d", math.round(self._hue)))
  self:_set_input_text("s", string.format("%d", math.round(self._saturation * 100)))
  self:_set_input_text("v", string.format("%d", math.round(self._value * 100)))
  self:_set_input_text("hex", string.format("#%02X%02X%02X", color[2], color[3], color[4]))

  if self._has_alpha then
    self:_set_input_text("a", string.format("%d", color[1]))
  end
end

ViewElementColorPicker._sync_widgets = function (self)
  local hue_red, hue_green, hue_blue = hsv_to_rgb(self._hue, 1, 1)
  local sv_content = self._widgets_by_name.sv.content
  local hue_content = self._widgets_by_name.hue.content

  sv_content.hue_color = { 255, hue_red, hue_green, hue_blue }
  sv_content.sv_x = self._saturation * PICKER_SIZE
  sv_content.sv_y = (1 - self._value) * PICKER_SIZE
  hue_content.hue_y = PICKER_SIZE * self._hue / 360
  self._widgets_by_name.preview.content.draft_color = self._draft_color

  if self._has_alpha then
    self._widgets_by_name.alpha.content.draft_color = self._draft_color
    self._widgets_by_name.alpha.content.alpha_y = PICKER_SIZE * (1 - self._draft_color[1] / 255)
  end

  self:_sync_fields()
end

ViewElementColorPicker._set_draft_color = function (self, color, hue, saturation, value)
  if not self._has_alpha then
    color[1] = 255
  end

  local changed = not colors_equal(self._draft_color, color)

  self._draft_color = color
  self._hue = hue
  self._saturation = saturation
  self._value = value

  self:_sync_widgets()

  if changed then
    self._entry.on_activated(copy_color(color), self._entry)
    self._entry.changed_callback()
    self._parent:update_color_widget_preview(self._entry, color)
  end
end

ViewElementColorPicker._set_from_hsv = function (self, hue, saturation, value)
  hue = math.clamp(hue, 0, 360)
  saturation = math.clamp(saturation, 0, 1)
  value = math.clamp(value, 0, 1)

  local red, green, blue = hsv_to_rgb(hue, saturation, value)
  local alpha = self._draft_color[1]

  self:_set_draft_color({ alpha, red, green, blue }, hue, saturation, value)
end

ViewElementColorPicker._set_from_rgb = function (self, red, green, blue)
  local hue, saturation, value = rgb_to_hsv(red, green, blue)

  if saturation == 0 then
    hue = self._hue
  end

  self:_set_draft_color({ self._draft_color[1], red, green, blue }, hue, saturation, value)
end

ViewElementColorPicker._set_alpha = function (self, alpha)
  local color = copy_color(self._draft_color)

  color[1] = clamp_integer(alpha, 0, 255)
  self:_set_draft_color(color, self._hue, self._saturation, self._value)
end

ViewElementColorPicker._on_sv_pointer_changed = function (self, normalized_x, normalized_y)
  self:_commit_writing_fields()
  self:_set_from_hsv(self._hue, normalized_x, 1 - normalized_y)
end

ViewElementColorPicker._on_hue_pointer_changed = function (self, _, normalized_y)
  self:_commit_writing_fields()
  self:_set_from_hsv(normalized_y * 360, self._saturation, self._value)
end

ViewElementColorPicker._on_alpha_pointer_changed = function (self, _, normalized_y)
  self:_commit_writing_fields()
  self:_set_alpha((1 - normalized_y) * 255)
end

local function parse_integer(value, min_value, max_value)
  value = string.gsub(value or "", "%s", "")

  if not string.match(value, "^%d+$") then
    return nil
  end

  local number = tonumber(value)

  if number < min_value or number > max_value then
    return nil
  end

  return number
end

local function parse_hex(value)
  local red_hex, green_hex, blue_hex = string.match(value, "^#?([%x][%x])([%x][%x])([%x][%x])$")

  if not red_hex then
    return nil
  end

  return tonumber(red_hex, 16), tonumber(green_hex, 16), tonumber(blue_hex, 16)
end

local function is_field_input_valid(field_name, input)
  if field_name == "r" or field_name == "g" or field_name == "b" or field_name == "a" then
    return parse_integer(input, 0, 255) ~= nil
  elseif field_name == "h" then
    return parse_integer(input, 0, 360) ~= nil
  elseif field_name == "s" or field_name == "v" then
    return parse_integer(input, 0, 100) ~= nil
  elseif field_name == "hex" then
    return parse_hex(input) ~= nil
  end

  return false
end

ViewElementColorPicker._commit_field = function (self, field_name)
  local input = self._widgets_by_name["input_" .. field_name].content.input_text or ""
  local color = self._draft_color

  if field_name == "r" or field_name == "g" or field_name == "b" then
    local value = parse_integer(input, 0, 255)

    if value then
      local red, green, blue = color[2], color[3], color[4]

      if field_name == "r" then
        red = value
      elseif field_name == "g" then
        green = value
      else
        blue = value
      end

      self:_set_from_rgb(red, green, blue)
      return true
    end
  elseif field_name == "h" or field_name == "s" or field_name == "v" then
    local max_value = field_name == "h" and 360 or 100
    local value = parse_integer(input, 0, max_value)

    if value then
      local hue = self._hue
      local saturation = self._saturation
      local brightness = self._value

      if field_name == "h" then
        hue = value
      elseif field_name == "s" then
        saturation = value / 100
      else
        brightness = value / 100
      end

      self:_set_from_hsv(hue, saturation, brightness)
      return true
    end
  elseif field_name == "a" then
    local value = parse_integer(input, 0, 255)

    if value then
      self:_set_alpha(value)
      return true
    end
  elseif field_name == "hex" then
    local red, green, blue = parse_hex(input)

    if red then
      self:_set_from_rgb(red, green, blue)
      return true
    end
  end

  self:_sync_fields()

  return false
end

ViewElementColorPicker._commit_writing_fields = function (self)
  for i = 1, #self._field_names do
    local field_name = self._field_names[i]
    local content = self._widgets_by_name["input_" .. field_name].content

    if content.is_writing or self._field_writing[field_name] then
      self:_stop_field_writing(field_name)
    end
  end
end

ViewElementColorPicker._stop_field_writing = function (self, field_name)
  local content = self._widgets_by_name["input_" .. field_name].content

  content.is_writing = false
  self:_commit_field(field_name)

  TextInputUtils.clear_selection(content)
  content.hotspot.is_focused = false
  content.hotspot.is_selected = false
  self._field_writing[field_name] = false
end

ViewElementColorPicker._update_text_fields = function (self, input_service)
  if input_service:get("back") then
    local is_writing = false

    for i = 1, #self._field_names do
      local content = self._widgets_by_name["input_" .. self._field_names[i]].content
      is_writing = is_writing or content.is_writing
    end

    if is_writing then
      self:_commit_writing_fields()
    else
      self:_close()
    end
  end
end

ViewElementColorPicker._update_field_writing_state = function (self)
  for i = 1, #self._field_names do
    local field_name = self._field_names[i]
    local widget = self._widgets_by_name["input_" .. field_name]
    local content = widget.content
    local was_writing = self._field_writing[field_name]

    if content.is_writing and not was_writing then
      self._field_writing[field_name] = true
    elseif was_writing and not content.is_writing then
      self:_stop_field_writing(field_name)
    elseif not content.is_writing then
      TextInputUtils.clear_selection(content)
    end

    local is_valid = not content.is_writing or is_field_input_valid(field_name, content.input_text or "")

    TextInputUtils.update_validation_style(widget.style, is_valid)
  end
end

ViewElementColorPicker._handle_pointer_focus_change = function (self, input_service)
  if not input_service:get("left_pressed") or self._widgets_by_name.back_button.content.hotspot.on_pressed then
    return
  end

  local pressed_field

  for i = 1, #self._field_names do
    local field_name = self._field_names[i]

    if self._widgets_by_name["input_" .. field_name].content.hotspot.on_pressed then
      pressed_field = field_name

      break
    end
  end

  for i = 1, #self._field_names do
    local field_name = self._field_names[i]
    local content = self._widgets_by_name["input_" .. field_name].content

    if field_name ~= pressed_field and (content.is_writing or self._field_writing[field_name]) then
      self:_stop_field_writing(field_name)
    end
  end
end

ViewElementColorPicker._draw_widgets = function (self, dt, t, input_service, ui_renderer, render_settings)
  ViewElementColorPicker.super._draw_widgets(self, dt, t, input_service, ui_renderer, render_settings)
  self:_update_field_writing_state()
  self:_handle_pointer_focus_change(input_service)
end

ViewElementColorPicker._close = function (self)
  self:_commit_writing_fields()
  self._parent:close_color_picker()
end

ViewElementColorPicker.update = function (self, dt, t, input_service)
  local using_cursor_navigation = Managers.ui:using_cursor_navigation()

  if self._gamepad_using_cursor_navigation ~= using_cursor_navigation then
    self._gamepad_using_cursor_navigation = using_cursor_navigation
    ColorPickerGamepad.on_navigation_input_changed(self, using_cursor_navigation)
  end

  if not using_cursor_navigation then
    ColorPickerGamepad.update(self, dt, input_service)
  elseif self._widgets_by_name.back_button.content.hotspot.on_pressed then
    ColorPickerGamepad.clear(self)
    self:_close()
  else
    self:_update_text_fields(input_service)
  end

  return ViewElementColorPicker.super.update(self, dt, t, input_service)
end

return ViewElementColorPicker
