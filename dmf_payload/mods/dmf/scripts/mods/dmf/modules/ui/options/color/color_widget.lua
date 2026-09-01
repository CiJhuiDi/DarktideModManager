local dmf = get_mod("DMF")

local ColorUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/color/color_utils")
local ColorWidgetPasses = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/color/color_widget_passes")

local colors_equal = ColorUtils.equal
local copy_color = ColorUtils.copy

local ColorWidget = {}
local GAMEPAD_CHANNEL_SPEED = 150
local COLOR_VALUE_IDS = {
  "color_value_1",
  "color_value_2",
  "color_value_3",
  "color_value_4",
}

local function first_channel_index(has_alpha)
  return has_alpha and 1 or 2
end

local function stop_gamepad_channel_edit(content)
  content.gamepad_active_channel = nil
  content.gamepad_channel_value = nil
end

local function refresh_color_value_text(content)
  local first_channel = first_channel_index(content.entry.has_alpha)

  for i = first_channel, 4 do
    content[COLOR_VALUE_IDS[i]] = string.format("%.0f", content.preview_color[i])
  end

  content.color_value_text_dirty = false
end

local function current_color(entry)
  return dmf._get_setting_value(entry.mod_name, entry.setting_id) or entry.default_value
end

local function update_gamepad_channel(content, input_service, dt)
  local channel_index = content.gamepad_active_channel

  if not channel_index then
    return
  end

  local controller_axis = input_service:get("navigate_controller")
  local x_axis = controller_axis and controller_axis[1] or 0

  if x_axis == 0 then
    return
  end

  local value = math.clamp(content.gamepad_channel_value + x_axis * GAMEPAD_CHANNEL_SPEED * dt, 0, 255)

  content.gamepad_channel_value = value

  if content.preview_color[channel_index] == math.round(value) then
    return
  end

  content.preview_color[channel_index] = math.round(value)

  if not content.entry.has_alpha then
    content.preview_color[1] = 255
  end

  content.on_color_changed()
end

local function handle_gamepad_input(parent, content, input_service)
  if content.gamepad_active_channel then
    if input_service:get("confirm_pressed") or input_service:get("back") then
      stop_gamepad_channel_edit(content)
    end

    return false
  end

  local has_alpha = content.entry.has_alpha
  local first_channel = first_channel_index(has_alpha)
  local selected_control = content.gamepad_selected_control or "preview"

  if input_service:get("back") then
    content.gamepad_selected_control = nil

    return true
  elseif input_service:get("confirm_pressed") then
    if selected_control == "preview" then
      parent:show_color_picker(content.entry)
    else
      local channel_index = selected_control

      content.gamepad_active_channel = channel_index
      content.gamepad_channel_value = content.preview_color[channel_index]
    end
  elseif input_service:get("navigate_left_continuous") then
    if selected_control ~= "preview" then
      content.gamepad_selected_control = "preview"
    end
  elseif input_service:get("navigate_right_continuous") then
    if selected_control == "preview" then
      content.gamepad_selected_control = first_channel
    end
  elseif input_service:get("navigate_up_continuous") and selected_control ~= "preview" then
    content.gamepad_selected_control = math.max(selected_control - 1, first_channel)
  elseif input_service:get("navigate_down_continuous") and selected_control ~= "preview" then
    content.gamepad_selected_control = math.min(selected_control + 1, 4)
  end

  return false
end

ColorWidget.create_blueprint = function (settings_grid_width, settings_value_width, settings_value_height)
  return {
    size = {
      settings_grid_width,
      settings_value_height,
    },
    pass_template_function = function (parent_, entry, size)
      return ColorWidgetPasses.create(size[1], size[2], settings_value_width, entry.has_alpha)
    end,
    init = function (parent, widget, entry, callback_name, changed_callback_name)
      local content = widget.content
      local color = current_color(entry)

      content.text = entry.display_name or Managers.localization:localize("loc_settings_option_unavailable")
      content.entry = entry
      content.preview_color = copy_color(color)
      content.color_value_text_dirty = true
      content.preview_hotspot.use_is_focused = true
      content.hotspot.pressed_callback = function ()
        if not entry.disabled and not Managers.ui:using_cursor_navigation() then
          callback(parent, callback_name, widget, entry)()
        end
      end
      content.gamepad_input_handler = function (input_service)
        return handle_gamepad_input(parent, content, input_service)
      end
      content.on_navigation_input_changed = function ()
        ColorWidgetPasses.stop_drag(content)
        stop_gamepad_channel_edit(content)
        content.gamepad_selected_control = nil
      end
      content.on_color_changed = function ()
        content.color_value_text_dirty = true
        entry.on_activated(copy_color(content.preview_color), entry)
        entry.changed_callback()
      end

      entry.changed_callback = function ()
        callback(parent, changed_callback_name, widget, entry)()
      end

      refresh_color_value_text(content)
    end,
    update = function (parent, widget, input_service, dt)
      local content = widget.content
      local entry = content.entry
      local is_disabled = entry.disabled or false
      local drag_active = content.drag_active and not is_disabled
      local using_gamepad = not parent:using_cursor_navigation()

      content.disabled = is_disabled

      if not content.exclusive_focus or not using_gamepad then
        content.gamepad_selected_control = nil
        stop_gamepad_channel_edit(content)
      elseif not content.gamepad_selected_control then
        content.gamepad_selected_control = "preview"
      end

      if content.preview_hotspot.on_pressed and not is_disabled and not using_gamepad then
        parent:show_color_picker(entry)
      elseif not drag_active and not content.gamepad_active_channel then
        local setting_color = current_color(entry)

        if not colors_equal(content.preview_color, setting_color) then
          content.preview_color = copy_color(setting_color)
          content.color_value_text_dirty = true
        end
      end

      if drag_active and not parent._selected_settings_widget then
        parent:set_exclusive_focus_on_grid_widget(widget.name)
      elseif content.drag_previously_active and not drag_active then
        parent:set_exclusive_focus_on_grid_widget(nil)
      end

      if content.gamepad_active_channel then
        update_gamepad_channel(content, input_service, dt)
      end

      content.drag_previously_active = drag_active

      if content.color_value_text_dirty then
        refresh_color_value_text(content)
      end

      return true
    end,
  }
end

return ColorWidget
