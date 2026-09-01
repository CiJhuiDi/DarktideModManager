local dmf = get_mod("DMF")

local TextInputUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/text_input_utils")

local UIRenderer = require("scripts/managers/ui/ui_renderer")

local NumericInput = {}

local INPUT_HORIZONTAL_PADDING = 10
local MIN_INPUT_WIDTH = 64
local ALIGNMENT_PASS_INDEX = 5

local function number_format(num_decimals)
  return string.format("%%.%df", num_decimals)
end

local function format_value(format, value)
  return string.format(format, value)
end

local function max_input_length(entry)
  local format = number_format(entry.num_decimals)
  local min_text = format_value(format, entry.min_value)
  local max_text = format_value(format, entry.max_value)

  return math.max(#min_text, #max_text)
end

local function find_value_pass(passes)
  for i = 1, #passes do
    local pass = passes[i]

    if pass.value_id == "value_text" then
      return pass
    end
  end
end

local function writing_visibility(original_visibility)
  return function (content, style)
    return content.is_writing and (not original_visibility or original_visibility(content, style))
  end
end

local function create_alignment_pass(input_x, input_width)
  return {
    pass_type = "logic",
    value = function (pass_, ui_renderer, ui_style, content)
      local display_style = ui_style.parent.display_text
      local input_text = content.input_text or ""

      if content.numeric_aligned_text == input_text then
        return
      end

      local text_width = UIRenderer.text_size(ui_renderer, input_text, display_style.font_type, display_style.font_size)

      display_style.offset[1] = input_x + input_width - INPUT_HORIZONTAL_PADDING - text_width
      content.numeric_aligned_text = input_text
    end,
  }
end

NumericInput.add_passes = function (parent, entry, passes, input_height)
  local value_pass = find_value_pass(passes)
  local value_style = value_pass.style
  local input_passes = TextInputUtils.clone_simple_input_field()
  local display_style

  for i = 1, #input_passes do
    local pass = input_passes[i]

    if pass.style_id == "display_text" then
      display_style = pass.style
      display_style.font_type = value_style.font_type
      display_style.font_size = value_style.font_size

      break
    end
  end

  local input_length = max_input_length(entry)
  local measurement_text = string.rep("A", input_length)
  local text_width = UIRenderer.text_size(parent._ui_offscreen_renderer, measurement_text, display_style.font_type,
                                           display_style.font_size)
  local input_width = math.max(math.ceil(text_width) + INPUT_HORIZONTAL_PADDING * 2, MIN_INPUT_WIDTH)
  local value_right = value_style.offset[1] + value_style.size[1]
  local input_x = math.floor(value_right - input_width)
  local value_visibility = value_pass.visibility_function

  value_pass.visibility_function = function (content, style)
    return not content.is_writing and (not value_visibility or value_visibility(content, style))
  end

  -- This runs immediately before the native caret and selection layout passes.
  table.insert(input_passes, ALIGNMENT_PASS_INDEX, create_alignment_pass(input_x, input_width))

  for i = 1, #input_passes do
    local pass = input_passes[i]
    local style_id = pass.style_id or pass.value_id

    if pass.pass_type == "hotspot" then
      pass.content_id = "input_hotspot"
      pass.style_id = "input_hotspot"
      pass.content = {
        use_is_focused = false,
      }
      style_id = pass.style_id
    elseif pass.pass_type ~= "logic" then
      pass.visibility_function = writing_visibility(pass.visibility_function)
    end

    if style_id == "limit_text" then
      pass.visibility_function = function ()
        return false
      end
    elseif style_id == "focused" then
      pass.visibility_function = function (content)
        return content.is_writing
      end
    end

    if style_id then
      local style = pass.style or {}

      pass.style = style
      style.offset = style.offset or { 0, 0, 0 }
      style.offset[1] = style.offset[1] + input_x

      if style_id == "background" or style_id == "focused" or style_id == "input_hotspot" then
        style.size = { input_width, input_height }
      elseif style_id == "baseline" then
        style.size = { input_width, 2 }
        style.vertical_alignment = "top"
        style.offset[2] = input_height - 2
      elseif pass.pass_type == "text" or pass.pass_type == "text_input" then
        style.size = { input_width, input_height }
        style.font_type = value_style.font_type
        style.font_size = value_style.font_size
      end
    end
  end

  table.append(passes, input_passes)

  return passes
end

local function set_input_text(content, text)
  content.input_text = text
  content.display_text = text
  content.numeric_aligned_text = nil
  content._input_text = nil
  content.caret_position = Utf8.string_length(text) + 1
  content._caret_position = nil
  content._input_text_first_visible_pos = 1
  content.force_caret_update = true
end

local function parse_input(entry, text, max_length)
  if Utf8.string_length(text) > max_length then
    return nil
  end

  local integer, fraction = string.match(text, "^(-?%d+)%.(%d+)$")

  if not integer then
    integer = string.match(text, "^(-?%d+)$")
  elseif #fraction > entry.num_decimals then
    return nil
  end

  if not integer then
    return nil
  end

  local value = tonumber(text)

  if not value or value < entry.min_value or value > entry.max_value then
    return nil
  end

  return value
end

local function sync_input(content, text)
  if content.input_text ~= text then
    set_input_text(content, text)
  end
end

local function sync_current_value(content, entry)
  local value = entry.get_function(entry) or entry.default_value

  sync_input(content, format_value(content.numeric_number_format, value))
end

local function finish_editing(widget, entry)
  local content = widget.content
  local value = parse_input(entry, content.input_text or "", content.max_length)
  local current_value = entry.get_function(entry) or entry.default_value

  content.is_writing = false
  content.numeric_input_was_writing = false
  content.input_hotspot.is_selected = false

  if value and value ~= current_value then
    entry.on_activated(value, entry)
    entry.changed_callback(value)
  end

  TextInputUtils.clear_selection(content)
  sync_current_value(content, entry)
  TextInputUtils.update_validation_style(widget.style, true)
end

NumericInput.init = function (widget, entry)
  local content = widget.content
  local format = number_format(entry.num_decimals)

  content.numeric_number_format = format
  content.max_length = max_input_length(entry)
  content.show_length_limit = false
  content.close_on_backspace = false
  content.numeric_input_was_writing = false
  content.input_hotspot.use_is_focused = false

  sync_current_value(content, entry)
end

NumericInput.sync = function (widget, text)
  sync_input(widget.content, text)
end

NumericInput.update = function (parent, widget, entry, input_service, using_gamepad, is_disabled)
  local content = widget.content
  local input_hotspot = content.input_hotspot
  local is_writing = content.is_writing
  local was_writing = content.numeric_input_was_writing

  input_hotspot.disabled = is_disabled or using_gamepad

  if was_writing and not is_writing then
    finish_editing(widget, entry)

    return true
  elseif not is_writing then
    input_hotspot.is_selected = false
    TextInputUtils.clear_selection(content)
    TextInputUtils.update_validation_style(widget.style, true)

    return false
  end

  content.numeric_input_was_writing = true
  input_hotspot.is_selected = true
  parent.is_text_input_focused = true
  parent._selected_settings_widget = widget

  local input_valid = parse_input(entry, content.input_text or "", content.max_length) ~= nil
  local clicked_away = input_service and input_service:get("left_pressed") and not input_hotspot.is_hover
  local confirmed = input_service and input_service:get("confirm_pressed")
  local cancelled = input_service and input_service:get("back")

  TextInputUtils.update_validation_style(widget.style, input_valid)

  if clicked_away or confirmed or cancelled or using_gamepad or is_disabled then
    finish_editing(widget, entry)
  end

  return true
end

return NumericInput
