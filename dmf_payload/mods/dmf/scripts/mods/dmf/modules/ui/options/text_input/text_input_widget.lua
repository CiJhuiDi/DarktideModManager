local TextInputPassTemplates = require("scripts/ui/pass_templates/text_input_pass_templates")
local UIFontSettings = require("scripts/managers/ui/ui_font_settings")

local TextInputWidget = {}

local label_style = table.clone(UIFontSettings.header_4)
label_style.offset = { 30, 0, 3 }
label_style.text_horizontal_alignment = "left"
label_style.text_vertical_alignment = "center"
label_style.text_color = Color.terminal_text_body(255, true)

local function create_passes(size, value_width, value_height)
  local passes = table.clone(TextInputPassTemplates.simple_input_field)

  passes[#passes + 1] = {
    value_id = "text",
    pass_type = "text",
    style = label_style,
  }

  local x_offset = size[1] - value_width

  for i = 1, #passes do
    local pass = passes[i]
    local style_id = pass.style_id or pass.value_id

    if style_id ~= "text" then
      pass.style = pass.style or {}
      pass.style.offset = pass.style.offset or { 0, 0, 0 }
      pass.style.offset[1] = pass.style.offset[1] + x_offset

      if style_id == "background" or style_id == "focused" or pass.pass_type == "hotspot" then
        pass.style.size = { value_width, value_height }
      elseif style_id == "baseline" then
        pass.style.size = { value_width, 2 }
        pass.style.vertical_alignment = "top"
        pass.style.offset[2] = value_height - 2
      end

      if pass.pass_type == "text" or pass.pass_type == "text_input" then
        pass.style.size = { value_width - 20, value_height }
        pass.style.offset[1] = pass.style.offset[1] + 10
        pass.style.text_horizontal_alignment = "left"
        pass.style.text_vertical_alignment = "center"
      end
    end
  end

  return passes
end

TextInputWidget.create_blueprint = function (grid_width, value_width, value_height)
  return {
    size = { grid_width, value_height },
    pass_template_function = function (parent_, config_, size)
      return create_passes(size, value_width, value_height)
    end,
    init = function (parent_, widget, entry, callback_name_, changed_callback_name_)
      local content = widget.content

      if type(entry.default_value) == "table" then
        entry.default_value = entry.default_value[1] or ""
      end

      local current_value = entry.get_function and entry.get_function() or ""

      if type(current_value) == "table" then
        current_value = current_value[1] or ""
      end

      content.input_text = current_value
      content.text = entry.display_name or Managers.localization:localize("loc_settings_option_unavailable")
      content.entry = entry
      content.hint_text = "Enter text..."

      -- text_input reuses keybind initialization, which stores its default value in a table.
      entry.on_activated(content.input_text, entry)

      entry.changed_callback = function (changed_value)
        if entry.on_activated then
          entry.on_activated(changed_value, entry)
        end
      end
    end,
    update = function (parent, widget, input_service)
      local content = widget.content
      local entry = content.entry

      if content.is_writing and input_service then
        local clicked_away = input_service:get("left_pressed") and not content.hotspot.is_hover
        local pressed_escape = input_service:get("back")

        if clicked_away or pressed_escape then
          content.is_writing = false
          entry.changed_callback(content.input_text)
        end
      end

      if content.hotspot.is_focused or content.is_writing then
        parent.is_text_input_focused = true
      end

      if content.is_writing then
        parent._selected_settings_widget = widget
      end
    end,
  }
end

return TextInputWidget
