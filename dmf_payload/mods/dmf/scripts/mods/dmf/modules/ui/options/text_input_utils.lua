local TextInputPassTemplates = require("scripts/ui/pass_templates/text_input_pass_templates")

local TextInputUtils = {}

local VALID_TEXT_CHANNEL = 255
local INVALID_TEXT_CHANNEL = 70

TextInputUtils.clear_selection = function (content)
  content.selected_text = nil
  content._selection_start = nil
  content._selection_end = nil
  content._selection_changed = nil
  content._is_selecting = nil
  content.last_input = nil
end

local function update_writing_state(hotspot_content)
  if not hotspot_content.on_pressed then
    return
  end

  hotspot_content.double_click_timer = 0

  local content = hotspot_content.parent

  if not content.is_writing then
    content.is_writing = true

    local input_text = content.input_text

    if input_text and Utf8.string_length(input_text) > 0 and not content.selected_text then
      content.input_text = ""
      content.selected_text = input_text
    end
  elseif content.selected_text and content.selected_text ~= "" then
    TextInputUtils.clear_selection(content)
  else
    content.is_writing = false
  end
end

TextInputUtils.clone_simple_input_field = function ()
  local passes = table.clone(TextInputPassTemplates.simple_input_field)

  for i = 1, #passes do
    local pass = passes[i]

    if pass.pass_type == "hotspot" then
      pass.change_function = update_writing_state

      break
    end
  end

  return passes
end

TextInputUtils.update_validation_style = function (style, is_valid)
  local text_color = style.display_text.text_color

  text_color[2] = VALID_TEXT_CHANNEL
  text_color[3] = is_valid and VALID_TEXT_CHANNEL or INVALID_TEXT_CHANNEL
  text_color[4] = is_valid and VALID_TEXT_CHANNEL or INVALID_TEXT_CHANNEL
end

return TextInputUtils
