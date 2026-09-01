local dmf = get_mod("DMF")

local TextInputUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/text_input_utils")

local FilterInput = {}
local CLEAR_BUTTON_WIDTH = 40
local CLEAR_BUTTON_HEIGHT = 44
local CLEAR_ICON_SIZE = 24
local CLEAR_ICON = "content/ui/materials/icons/system/settings/category_interface"

local function has_input_text(content)
  content = content.parent or content

  return content.input_text and content.input_text ~= ""
end

FilterInput.create_passes = function ()
  local passes = TextInputUtils.clone_simple_input_field()

  for i = 1, #passes do
    local pass = passes[i]

    if pass.pass_type == "hotspot" then
      pass.content = pass.content or {}
      pass.content.use_is_focused = true
      pass.style = pass.style or {}
      pass.style.size_addition = { -CLEAR_BUTTON_WIDTH, 0 }
    elseif pass.style_id == "display_text" or pass.style_id == "active_placeholder" then
      pass.style.size_addition[1] = pass.style.size_addition[1] - CLEAR_BUTTON_WIDTH
    elseif pass.style_id == "limit_text" then
      pass.visibility_function = function ()
        return false
      end
    end
  end

  passes[#passes + 1] = {
    pass_type = "hotspot",
    content_id = "clear_hotspot",
    style_id = "clear_hotspot",
    style = {
      horizontal_alignment = "right",
      vertical_alignment = "center",
      size = { CLEAR_BUTTON_WIDTH, CLEAR_BUTTON_HEIGHT },
      offset = { 0, 0, 4 },
    },
    visibility_function = has_input_text,
    change_function = function (hotspot_content)
      if hotspot_content.on_pressed then
        FilterInput.clear(hotspot_content.parent)
      end
    end,
  }
  passes[#passes + 1] = {
    pass_type = "texture",
    value = CLEAR_ICON,
    style_id = "clear_icon",
    style = {
      horizontal_alignment = "right",
      vertical_alignment = "center",
      size = { CLEAR_ICON_SIZE, CLEAR_ICON_SIZE },
      offset = { -(CLEAR_BUTTON_WIDTH - CLEAR_ICON_SIZE) * 0.5, 0, 5 },
      color = Color.ui_grey_light(180, true),
    },
    visibility_function = has_input_text,
    change_function = function (content, style)
      style.color[1] = content.clear_hotspot.is_hover and 255 or 180
    end,
  }

  return passes
end

FilterInput.reset = function (content)
  content.input_text = ""
  content.display_text = ""
  content._input_text = nil
  content.caret_position = 1
  content._caret_position = nil
  content._input_text_first_visible_pos = 1
  content.force_caret_update = true
  content._blink_time = nil
  content.is_writing = false
  content.hotspot.is_focused = false
  content.hotspot.is_selected = false

  TextInputUtils.clear_selection(content)
end

FilterInput.finish_editing = function (content)
  content.is_writing = false
  TextInputUtils.clear_selection(content)
end

FilterInput.clear = function (content)
  content.input_text = ""
  content.display_text = ""
  content.caret_position = 1
  content._input_text_first_visible_pos = 1
  content.force_caret_update = true

  FilterInput.finish_editing(content)

  content.hotspot.is_selected = content.hotspot.is_focused or false
end

FilterInput.set_focused = function (content, focused)
  local hotspot = content.hotspot

  hotspot.is_focused = focused
  hotspot.is_selected = focused or content.is_writing
end

FilterInput.update = function (content, input_service, focused)
  local hotspot = content.hotspot

  if content.is_writing then
    local clicked_away = input_service:get("left_pressed") and not hotspot.is_hover

    if clicked_away then
      FilterInput.finish_editing(content)
    end
  else
    TextInputUtils.clear_selection(content)
  end

  hotspot.is_selected = focused or content.is_writing
end

return FilterInput
