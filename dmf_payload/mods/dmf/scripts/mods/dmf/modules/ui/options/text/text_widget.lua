local dmf = get_mod("DMF")

local TextInputUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/text_input_utils")

local ListHeaderPassTemplates = require("scripts/ui/pass_templates/list_header_templates")

local TextWidget = {}

local ENABLED_ALPHA = 255
local DISABLED_ALPHA = 128
local PLACEHOLDER_ENABLED_ALPHA = 200
local PLACEHOLDER_DISABLED_ALPHA = 100

local function create_passes(size, value_width, value_height)
  local x_offset = size[1] - value_width
  local passes = ListHeaderPassTemplates.list_header(x_offset, value_height, true)
  local input_passes = TextInputUtils.clone_simple_input_field()

  for i = 1, #input_passes do
    local pass = input_passes[i]
    local style_id = pass.style_id or pass.value_id

    if pass.pass_type == "hotspot" then
      pass.content_id = "input_hotspot"
      pass.style_id = "input_hotspot"
      pass.content = {
        use_is_focused = true,
      }
      style_id = pass.style_id
    end

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
      elseif style_id == "limit_text" then
        pass.visibility_function = function (content)
          return content.max_length and content.show_length_limit
        end
      end

      if pass.pass_type == "text" or pass.pass_type == "text_input" then
        pass.style.size = { value_width - 20, value_height }
        pass.style.offset[1] = pass.style.offset[1] + 10
        pass.style.text_vertical_alignment = "center"

        if style_id ~= "limit_text" then
          pass.style.text_horizontal_alignment = "left"
        end
      end

      if style_id == "focused" then
        pass.visibility_function = function (content)
          local hotspot = content.input_hotspot

          return not content.disabled and (hotspot.is_focused or hotspot.is_selected)
        end
      end
    end
  end

  passes[#passes + 1] = {
    pass_type = "logic",
    value = function (pass_, renderer_, style_, content)
      local hotspot = content.hotspot
      local input_hotspot = content.input_hotspot

      input_hotspot.force_disabled = hotspot.force_disabled
      input_hotspot.is_focused = hotspot.is_focused
    end,
  }

  table.append(passes, input_passes)

  return passes
end

local function is_text_valid(content, value)
  if content.max_length and Utf8.string_length(value) > content.max_length then
    return false
  end

  return not content.validate or content.validate(value)
end

local function restore_setting_value(content)
  local setting_value = content.setting_value

  content.input_text = setting_value
  content.display_text = setting_value
  content._input_text = nil
  content.caret_position = Utf8.string_length(setting_value) + 1
  content._caret_position = nil
  content._input_text_first_visible_pos = 1
  content.force_caret_update = true
end

local function finish_editing(content, entry)
  content.is_writing = false

  local input_text = content.input_text

  if not is_text_valid(content, input_text) then
    restore_setting_value(content)

    return
  end

  if input_text ~= content.setting_value then
    entry.changed_callback(input_text)
  end
end

local function update_disabled_style(style, is_disabled)
  local alpha = is_disabled and DISABLED_ALPHA or ENABLED_ALPHA

  style.background.color[1] = alpha
  style.baseline.color[1] = alpha
  style.display_text.text_color[1] = alpha
  style.limit_text.text_color[1] = alpha
  style.active_placeholder.text_color[1] = is_disabled and PLACEHOLDER_DISABLED_ALPHA or PLACEHOLDER_ENABLED_ALPHA
end

TextWidget.create_blueprint = function (grid_width, value_width, value_height)
  return {
    size = { grid_width, value_height },
    pass_template_function = function (parent_, config_, size)
      return create_passes(size, value_width, value_height)
    end,
    init = function (parent, widget, entry, callback_name_, changed_callback_name)
      local content = widget.content
      local current_value = entry.get_function()

      content.input_text = current_value
      content.max_length = entry.max_length
      content.placeholder_text = entry.placeholder_text
      content.setting_value = current_value
      content.show_length_limit = entry.show_length_limit
      content.validate = entry.validate
      content.text = entry.display_name or Managers.localization:localize("loc_settings_option_unavailable")
      content.entry = entry

      entry.changed_callback = function (changed_value)
        if entry.on_activated(changed_value) then
          content.setting_value = changed_value
          callback(parent, changed_callback_name, widget, entry)()
        end
      end
    end,
    update = function (parent, widget, input_service)
      local content = widget.content
      local entry = content.entry
      local hotspot = content.hotspot
      local input_hotspot = content.input_hotspot
      local is_disabled = entry.disabled or false

      content.disabled = is_disabled
      hotspot.disabled = is_disabled
      input_hotspot.disabled = is_disabled

      update_disabled_style(widget.style, is_disabled)

      if is_disabled and content.is_writing then
        finish_editing(content, entry)
      end

      if content.is_writing and input_service then
        local clicked_away = input_service:get("left_pressed") and not input_hotspot.is_hover
        local pressed_escape = input_service:get("back")

        if clicked_away or pressed_escape then
          finish_editing(content, entry)
        end
      end

      if not content.is_writing then
        local current_value = entry.get_function()

        if content.input_text ~= content.setting_value then
          finish_editing(content, entry)
        elseif content.setting_value ~= current_value then
          content.input_text = current_value
          content.setting_value = current_value
        end

        TextInputUtils.clear_selection(content)
      end

      if not is_disabled and (hotspot.is_focused or content.is_writing) then
        parent.is_text_input_focused = true
      end

      if content.is_writing then
        parent._selected_settings_widget = widget
      end

      TextInputUtils.update_validation_style(
        widget.style,
        not content.is_writing or is_text_valid(content, content.input_text)
      )
    end,
  }
end

return TextWidget
