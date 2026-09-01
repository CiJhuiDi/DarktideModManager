---@class DMFMod
local dmf = get_mod("DMF")

local _view_settings = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view_settings")
local ColorWidget = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/color/color_widget")
local NumericInput = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/numeric/numeric_input")
local TextInputWidget = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/text_input/text_input_widget")
local TextWidget = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/text/text_widget")

local ButtonPassTemplates = require("scripts/ui/pass_templates/button_pass_templates")
local CheckboxPassTemplates = require("scripts/ui/pass_templates/checkbox_pass_templates")
local DropdownPassTemplates = require("scripts/ui/pass_templates/dropdown_pass_templates")
local InputUtils = require("scripts/managers/input/input_utils")
local KeybindPassTemplates = require("scripts/ui/pass_templates/keybind_pass_templates")
local SliderPassTemplates = require("scripts/ui/pass_templates/slider_pass_templates")
local UIFontSettings = require("scripts/managers/ui/ui_font_settings")

local grid_size = _view_settings.grid_size
local grid_width = grid_size[1]

local settings_grid_width = 1000
local settings_value_width = 500
local settings_value_height = 64

local group_header_height = 50
local group_header_spacing = 20

local DEFAULT_NUM_DECIMALS = 0
local BUTTON_HOLD_INPUT_ACTION = "confirm_hold"
local BUTTON_HOLD_COLOR = Color.ui_terminal(255, true)
local BUTTON_DISABLED_HOLD_COLOR = Color.ui_grey_medium(255, true)

local _dropdown_deadzone = 0.25 -- 250ms delay before opening keybind popups
local _last_dropdown_pressed = -1

local value_font_style = table.clone(UIFontSettings.list_button)
value_font_style.offset = {
  settings_grid_width - settings_value_width + 25,
  0,
  8
}

local header_font_style = table.clone(UIFontSettings.header_2)
header_font_style.text_vertical_alignment = "bottom"

local function update_held_button_text(content)
  local hotspot = content.hotspot
  local color = hotspot.disabled and BUTTON_DISABLED_HOLD_COLOR or BUTTON_HOLD_COLOR
  local button_text = content.original_button_text
  local input_text

  if hotspot.gamepad_active then
    local service_type = "View"
    local alias_key = Managers.ui:get_input_alias_key(BUTTON_HOLD_INPUT_ACTION, service_type)

    input_text = InputUtils.input_text_for_current_input_device(service_type, alias_key)
  end

  if input_text then
    content.button_text = string.format(
      "{#color(%d,%d,%d)}%s %s{#reset()} %s",
      color[2], color[3], color[4], Localize("loc_input_hold"), input_text, button_text
    )
  else
    content.button_text = string.format(
      "{#color(%d,%d,%d)}%s{#reset()} %s",
      color[2], color[3], color[4], Localize("loc_input_hold"), button_text
    )
  end
end


local function button_pass_template(parent, config, size)
  local passes = ButtonPassTemplates.settings_button(size[1], settings_value_height, settings_value_width, true)

  if config.button_trigger ~= "held" then
    return passes
  end

  local header_width = size[1] - settings_value_width
  local hold_pass = {
    pass_type = "rect",
    style_id = "hold",
    style = {
      horizontal_alignment = "left",
      vertical_alignment = "top",
      color = { 150, 0, 0, 0 },
      offset = { header_width, 0, 3 },
      size = { 0, settings_value_height },
    },
    change_function = function (content, style)
      style.size[1] = settings_value_width * (content.hold_progress or 0)
    end,
  }

  for i = 1, #passes do
    local pass = passes[i]

    if pass.value_id == "button_text" then
      local change_function = pass.change_function

      pass.change_function = function (content, style)
        update_held_button_text(content)
        change_function(content, style)
      end

      table.insert(passes, i, hold_pass)

      break
    end
  end

  return passes
end


local blueprints = {
  spacing_vertical = {
    size = {
      grid_width,
      20
    }
  },
  settings_button = {
    size = {
      grid_width,
      settings_value_height
    },
    pass_template = ButtonPassTemplates.list_button,
    init = function (parent, widget, entry, callback_name, changed_callback_name)
      local content = widget.content
      local hotspot = content.hotspot

      hotspot.pressed_callback = function ()
        local is_disabled = entry.disabled or false

        if is_disabled then
          return
        end

        callback(parent, callback_name, widget, entry)()
      end

      local display_name = entry.display_name
      content.text = display_name
      content.entry = entry
    end
  },
  button = {
    size = {
      settings_grid_width,
      settings_value_height
    },
    pass_template_function = button_pass_template,
    init = function (parent, widget, entry, callback_name, changed_callback_name)
      local content = widget.content
      local hotspot = content.hotspot

      content.text = entry.display_name
      content.button_text = entry.button_text
      content.original_button_text = entry.button_text
      content.entry = entry

      local pressed_callback = function ()
        if entry.disabled then
          return
        end

        callback(parent, callback_name, widget, entry)()
      end

      if entry.button_trigger == "held" then
        content.timer = entry.button_hold_duration
        content.current_timer = 0
        content.hold_progress = 0
        content.start_delay = 0
        content.input_action = BUTTON_HOLD_INPUT_ACTION
        content.keep_hold_active = false
        content.complete_function = pressed_callback
        hotspot.pressed_callback = nil
      else
        hotspot.pressed_callback = pressed_callback
      end
    end,
    update = function (parent, widget, input_service, dt, t)
      local content = widget.content
      local entry = content.entry
      local is_disabled = entry.disabled or false

      content.disabled = is_disabled
      content.hotspot.disabled = is_disabled

      if entry.button_trigger == "held" then
        ButtonPassTemplates.terminal_button_hold_small.update(parent, widget, {
          input_service = input_service,
        }, dt)
      end
    end,
  },
  group_header = {
    size = {
      settings_grid_width,
      group_header_height
    },
    spacing_before = group_header_spacing,
    pass_template = {
      {
        pass_type = "text",
        value_id = "text",
        style = header_font_style,
        value = Localize("loc_settings_option_unavailable")
      }
    },
    init = function (parent, widget, entry, callback_name, changed_callback_name)
      local content = widget.content
      local display_name = entry.display_name
      content.text = display_name
    end
  },
  checkbox = {
    size = {
      settings_grid_width,
      settings_value_height
    },
    pass_template_function = function (parent, config, size)
      return CheckboxPassTemplates.settings_checkbox(size[1], settings_value_height, settings_value_width, 2, true)
    end,
    init = function (parent, widget, entry, callback_name, changed_callback_name)
      local content = widget.content
      local display_name = entry.display_name or Managers.localization:localize("loc_settings_option_unavailable")
      content.text = display_name
      content.entry = entry

      if entry.controls_sub_widgets then
        content.dynamic_visibility_value = entry:get_function()
      end

      for i = 1, 2 do
        local widget_option_id = "option_" .. i
        content[widget_option_id] = i == 1 and Managers.localization:localize("loc_setting_checkbox_on") or Managers.localization:localize("loc_setting_checkbox_off")
      end

      entry.changed_callback = function (changed_value)
        --callback(parent, callback_name, widget, entry)()
        callback(parent, changed_callback_name, widget, entry, changed_value)()
      end
    end,
    update = function (parent, widget, input_service, dt, t)
      local content = widget.content
      local entry = content.entry
      local value = entry:get_function()
      local on_activated = entry.on_activated
      local pass_input = true
      local hotspot = content.hotspot
      local is_disabled = entry.disabled or false
      content.disabled = is_disabled
      local new_value = nil

      if entry.controls_sub_widgets and content.dynamic_visibility_value ~= value then
        content.dynamic_visibility_value = value
        parent:cb_on_dynamic_setting_value_changed(widget, entry, value)
      end

      if hotspot.on_pressed and not parent._navigation_column_changed_this_frame and not is_disabled then
        new_value = not value
      end

      for i = 1, 2 do
        local widget_option_id = "option_hotspot_" .. i
        local option_hotspot = content[widget_option_id]
        local is_selected = value and i == 1 or not value and i == 2
        option_hotspot.is_selected = is_selected
      end

      if new_value ~= nil and new_value ~= value then
        on_activated(new_value, entry)
        entry.changed_callback(new_value)
      end
    end
  }
}

blueprints.color = ColorWidget.create_blueprint(settings_grid_width, settings_value_width, settings_value_height)

local function slider_init_function(parent, widget, entry, callback_name, changed_callback_name)
  local content = widget.content
  local display_name = entry.display_name or Managers.localization:localize("loc_settings_option_unavailable")
  content.text = display_name
  content.entry = entry
  content.area_length = settings_value_width
  content.step_size = entry.normalized_step_size

  if not entry.normalized_step_size and entry.step_size_value then
    local value_range = entry.max_value - entry.min_value
    content.step_size = entry.step_size_value / value_range
  end

  content.apply_on_drag = entry.apply_on_drag and true
  local get_function = entry.get_function
  local value = get_function(entry)
  content.previous_slider_value = value
  content.slider_value = value

  entry.pressed_callback = function ()
    local is_disabled = entry.is_disabled

    if is_disabled then
      return
    end

    callback(parent, callback_name, widget, entry)()
  end

  entry.changed_callback = function (changed_value)
    callback(parent, changed_callback_name, widget, entry)()
  end
end

blueprints.percent_slider = {
  size = {
    settings_grid_width,
    settings_value_height
  },
  pass_template_function = function (parent, config, size)
    return SliderPassTemplates.settings_percent_slider(size[1], settings_value_height, settings_value_width, true)
  end,
  init = function (parent, widget, entry, callback_name, changed_callback_name)
    slider_init_function(parent, widget, entry, callback_name, changed_callback_name)
  end,
  update = function (parent, widget, input_service, dt, t)
    local content = widget.content
    local entry = content.entry
    local pass_input = true
    local is_disabled = entry.disabled or false
    content.disabled = is_disabled
    local using_gamepad = not parent:using_cursor_navigation()
    local get_function = entry.get_function
    local value = get_function(entry) / 100
    local on_activated = entry.on_activated
    local format_value_function = entry.format_value_function
    local drag_value, new_value = nil
    local apply_on_drag = content.apply_on_drag and not is_disabled
    local drag_active = content.drag_active and not is_disabled
    local focused = using_gamepad and content.exclusive_focus and not is_disabled

    if drag_active or focused then
      if not parent._selected_settings_widget then
        parent:set_exclusive_focus_on_grid_widget(widget.name)
      end

      local slider_value = content.slider_value
      drag_value = slider_value or get_function(entry) / 100
    elseif not focused then
      local previous_slider_value = content.previous_slider_value
      local slider_value = content.slider_value

      if content.drag_previously_active then
        parent:set_exclusive_focus_on_grid_widget(nil)

        if previous_slider_value ~= slider_value then
          new_value = slider_value
          drag_value = new_value or get_function(entry) / 100
        end
      elseif value ~= slider_value then
        content.slider_value = value
        content.previous_slider_value = value
        content.scroll_add = nil
      end

      content.previous_slider_value = slider_value
    end

    content.drag_previously_active = drag_active
    local display_value = format_value_function((drag_value or value) * 100)

    if display_value then
      content.value_text = display_value
    end

    local hotspot = content.hotspot

    if hotspot.on_pressed and not is_disabled then
      if focused then
        new_value = content.slider_value
      elseif using_gamepad and entry.pressed_callback then
        entry.pressed_callback()
      end
    end

    if focused and parent:can_exit() then
      parent:set_can_exit(false)
    end

    if apply_on_drag and drag_value and not new_value and content.slider_value ~= content.previous_slider_value then
      new_value = content.slider_value
    end

    if new_value then
      on_activated(new_value * 100, entry)
      entry.changed_callback(new_value)

      content.slider_value = new_value
      content.previous_slider_value = new_value
      content.scroll_add = nil
    end

    return pass_input
  end
}

blueprints.value_slider = {
  size = {
    settings_grid_width,
    settings_value_height
  },
  pass_template_function = function (parent, config, size)
    local passes = SliderPassTemplates.settings_value_slider(size[1], settings_value_height, settings_value_width, true)

    return NumericInput.add_passes(parent, config, passes, settings_value_height)
  end,
  init = function (parent, widget, entry, callback_name, changed_callback_name)
    slider_init_function(parent, widget, entry, callback_name, changed_callback_name)
    NumericInput.init(widget, entry)
  end,
  update = function (parent, widget, input_service, dt, t)
    local content = widget.content
    local entry = content.entry
    local pass_input = true
    local is_disabled = entry.disabled or false
    content.disabled = is_disabled
    local using_gamepad = not parent:using_cursor_navigation()

    if NumericInput.update(parent, widget, entry, input_service, using_gamepad, is_disabled) then
      return false
    end

    local min_value = entry.min_value
    local max_value = entry.max_value
    local get_function = entry.get_function
    local explode_function = entry.explode_function
    local value = get_function(entry) or entry.default_value
    local normalized_value = math.normalize_01(value, min_value, max_value)
    local on_activated = entry.on_activated
    local format_value_function = entry.format_value_function
    local drag_value, new_normalized_value = nil
    local apply_on_drag = content.apply_on_drag and not is_disabled
    local drag_active = content.drag_active and not is_disabled
    local drag_previously_active = content.drag_previously_active
    local focused = content.exclusive_focus and using_gamepad and not is_disabled

    if drag_active or focused then
      if not parent._selected_settings_widget then
        parent:set_exclusive_focus_on_grid_widget(widget.name)
      end

      local slider_value = content.slider_value
      drag_value = slider_value and explode_function(slider_value, entry) or get_function(entry)
    elseif not focused or drag_previously_active then
      local previous_slider_value = content.previous_slider_value
      local slider_value = content.slider_value

      if drag_previously_active then
        parent:set_exclusive_focus_on_grid_widget(nil)

        if previous_slider_value ~= slider_value then
          new_normalized_value = slider_value
          drag_value = slider_value and explode_function(slider_value, entry) or get_function(entry)
        end
      elseif normalized_value ~= slider_value then
        content.slider_value = normalized_value
        content.previous_slider_value = normalized_value
        content.scroll_add = nil
      end

      content.previous_slider_value = slider_value
    end

    content.drag_previously_active = drag_active
    local display_value = format_value_function(drag_value or value)

    if display_value then
      content.value_text = entry.unit_text and string.format("%s %s", display_value, entry.unit_text) or display_value
      NumericInput.sync(widget, display_value)
    end

    local hotspot = content.hotspot

    if hotspot.on_pressed then
      if focused then
        new_normalized_value = content.slider_value
      elseif using_gamepad and entry.pressed_callback then
        entry.pressed_callback()
      end
    end

    if focused and parent:can_exit() then
      parent:set_can_exit(false)
    end

    if apply_on_drag and drag_value and not new_normalized_value and content.slider_value ~= content.previous_slider_value then
      new_normalized_value = content.slider_value
    end

    if new_normalized_value then
      new_normalized_value = math.clamp(new_normalized_value, 0, 1)

      local new_value = explode_function(new_normalized_value, entry)
      new_normalized_value = math.normalize_01(new_value, min_value, max_value)

      on_activated(new_value, entry)
      entry.changed_callback(new_value)

      content.slider_value = new_normalized_value
      content.previous_slider_value = new_normalized_value
      content.scroll_add = nil
    end

    return pass_input
  end
}

blueprints.slider = {
  size = {
    settings_grid_width,
    settings_value_height
  },
  pass_template_function = function (parent, config, size)
    return SliderPassTemplates.settings_value_slider(size[1], settings_value_height, settings_value_width, true)
  end,
  init = function (parent, widget, entry, callback_name, changed_callback_name)
    local content = widget.content
    local display_name = entry.display_name or Managers.localization:localize("loc_settings_option_unavailable")
    content.text = display_name
    content.entry = entry
    content.area_length = settings_value_width
    content.step_size = entry.step_size_fraction
    content.apply_on_drag = entry.apply_on_drag and true
    local get_function = entry.get_function
    local value, value_fraction = get_function(entry)
    content.previous_slider_value = value_fraction
    content.slider_value = value_fraction
    entry.pressed_callback = callback(parent, callback_name, widget, entry)

    entry.changed_callback = function (changed_value)
      callback(parent, changed_callback_name, widget, entry)()
    end
  end,
  update = function (parent, widget, input_service, dt, t)
    local content = widget.content
    local entry = content.entry
    local pass_input = true
    local is_disabled = entry.disabled or false
    content.disabled = is_disabled
    local using_gamepad = not parent:using_cursor_navigation()
    local get_function = entry.get_function
    local value, value_fraction = get_function(entry)
    local on_activated = entry.on_activated
    local format_value_function = entry.format_value_function
    local num_decimals = entry.num_decimals
    local drag_value, new_value_fraction = nil
    local apply_on_drag = entry.apply_on_drag and not is_disabled
    local drag_active = content.drag_active and not is_disabled
    local drag_previously_active = content.drag_previously_active
    local focused = content.exclusive_focus and using_gamepad and not is_disabled

    if drag_active or focused then
      drag_value = math.lerp(entry.min_value, entry.max_value, content.slider_value)
    elseif not focused or drag_previously_active then
      local previous_slider_value = content.previous_slider_value
      local slider_value = content.slider_value

      if drag_previously_active then
        if previous_slider_value ~= slider_value then
          new_value_fraction = slider_value
          drag_value = math.lerp(entry.min_value, entry.max_value, new_value_fraction)
        end
      elseif value_fraction ~= slider_value then
        content.slider_value = value_fraction
        content.previous_slider_value = value_fraction
        content.scroll_add = nil
      end

      content.previous_slider_value = slider_value
    end

    content.drag_previously_active = drag_active
    local display_value = nil

    if format_value_function then
      display_value = format_value_function(entry, drag_value or value)
    else
      local number_format = string.format("%%.%sf", num_decimals or DEFAULT_NUM_DECIMALS)
      display_value = string.format(number_format, drag_value or value)
    end

    if display_value then
      content.value_text = display_value
    end

    local hotspot = content.hotspot

    if hotspot.on_pressed and not is_disabled then
      if focused then
        new_value_fraction = content.slider_value
      elseif not hotspot.is_hover then
        entry.pressed_callback()
      end
    end

    if focused and parent:can_exit() then
      parent:set_can_exit(false)
    end

    if apply_on_drag and drag_value and not new_value_fraction and content.slider_value ~= content.previous_slider_value then
      new_value_fraction = content.slider_value
    end

    if new_value_fraction then
      local new_value = math.lerp(entry.min_value, entry.max_value, new_value_fraction)

      on_activated(new_value, entry)
      entry.changed_callback(new_value)

      content.slider_value = new_value_fraction
      content.previous_slider_value = new_value_fraction
      content.scroll_add = nil
    end

    return pass_input
  end
}

local max_visible_options = _view_settings.max_visible_dropdown_options or 5
local DROPDOWN_ICON_ANCHOR_STYLE_ID = "dropdown_icon_anchor"

local function update_dropdown_icon_anchor()
end

local function dropdown_icon_anchor_pass(pass_template)
  local value_icon_pass_index
  local value_icon_style

  for i = 1, #pass_template do
    local pass = pass_template[i]

    if pass.style_id == "icon" then
      value_icon_pass_index = i
      value_icon_style = pass.style

      break
    end
  end

  local icon_center_x = value_icon_style.offset[1] + value_icon_style.size[1] * 0.5
  local anchor_pass = {
    pass_type = "logic",
    style_id = DROPDOWN_ICON_ANCHOR_STYLE_ID,
    value = update_dropdown_icon_anchor,
    style = {
      horizontal_alignment = "right",
      vertical_alignment = "center",
      size = { 0, 0 },
      offset = {
        icon_center_x - settings_grid_width,
        0,
        0,
      },
    },
  }

  table.insert(pass_template, value_icon_pass_index, anchor_pass)

  for i = value_icon_pass_index + 1, #pass_template do
    local pass = pass_template[i]
    local style_id = pass.style_id

    if style_id == "icon" or style_id and string.match(style_id, "^option_icon_%d+$") then
      local style = pass.style

      style.inherit_pass_transform = DROPDOWN_ICON_ANCHOR_STYLE_ID
      style.horizontal_alignment = "center"
      style.vertical_alignment = "center"
      style.offset[1] = 0
    end
  end

  return pass_template
end

local function apply_dropdown_icon_style(style, default_style, icon_style)
  table.create_copy(style, default_style)

  if not icon_style then
    return
  end

  table.merge_recursive(style, icon_style)

  local offset = icon_style.offset

  if offset then
    for i = 1, #default_style.offset do
      style.offset[i] = default_style.offset[i] + (offset[i] or 0)
    end
  end
end

blueprints.dropdown = {
  size = {
    settings_grid_width,
    settings_value_height
  },
  pass_template_function = function (parent, entry, size)
    local has_options_function = entry.options_function ~= nil
    local has_dynamic_contents = entry.has_dynamic_contents
    local display_name = entry.display_name or Localize("loc_settings_option_unavailable")
    local options = entry.options_function and entry.options_function() or entry.options
    local num_visible_options = math.min(#options, max_visible_options)

    local pass_template = DropdownPassTemplates.settings_dropdown(
      size[1],
      settings_value_height,
      settings_value_width,
      num_visible_options,
      true
    )

    return dropdown_icon_anchor_pass(pass_template)
  end,
  init = function (parent, widget, entry, callback_name, changed_callback_name)
    local content = widget.content
    local display_name = entry.display_name or Managers.localization:localize("loc_settings_option_unavailable")
    content.text = display_name
    content.entry = entry
    local has_options_function = entry.options_function ~= nil
    local has_dynamic_contents = entry.has_dynamic_contents
    local options = entry.options or entry.options_function and entry.options_function()
    local num_options = #options
    local num_visible_options = math.min(num_options, max_visible_options)
    content.num_visible_options = num_visible_options
    local optional_num_decimals = entry.optional_num_decimals
    local number_format = string.format("%%.%sf", optional_num_decimals or DEFAULT_NUM_DECIMALS)

    local options_by_value = {}
    for i = 1, num_options do
      local option = options[i]
      options_by_value[option.value] = option
    end

    content.number_format = number_format
    content.options_by_value = options_by_value
    content.options = options
    local has_custom_icon_styles = false

    for i = 1, num_options do
      if options[i].icon_style then
        has_custom_icon_styles = true

        break
      end
    end

    if has_custom_icon_styles then
      content.default_icon_styles = {
        value = table.clone(widget.style.icon),
        options = {},
      }
      content.applied_option_icon_styles = {}

      for i = 1, num_visible_options do
        content.default_icon_styles.options[i] = table.clone(widget.style["option_icon_" .. i])
      end
    end

    content.hotspot.pressed_callback = function ()
      local is_disabled = entry.disabled or false

      if is_disabled then
        return
      end

      callback(parent, callback_name, widget, entry)()
    end

    local widget_type = widget.type
    local template = blueprints[widget_type]
    local size = template.size
    content.area_length = size[2] * num_visible_options
    local scroll_length = math.max(size[2] * num_options - content.area_length, 0)
    content.scroll_length = scroll_length
    local spacing = 0
    local scroll_amount = scroll_length > 0 and (size[2] + spacing) / scroll_length or 0
    content.scroll_amount = scroll_amount
    local value = entry.get_function and entry:get_function() or entry.default_value

    if entry.controls_sub_widgets then
      content.dynamic_visibility_value = value
    end

    entry.changed_callback = function (changed_value)
      callback(parent, changed_callback_name, widget, entry, changed_value)()
    end
  end,
  update = function (parent, widget, input_service, dt, t)
    local content = widget.content
    local entry = content.entry
    local pass_input = true
    local is_disabled = entry.disabled or false
    content.disabled = is_disabled
    local using_gamepad = not parent:using_cursor_navigation()
    local offset = widget.offset
    local style = widget.style
    local options = content.options
    local options_by_value = content.options_by_value
    local num_visible_options = content.num_visible_options
    local num_options = #options
    local focused = content.exclusive_focus and not is_disabled

    if focused and parent:can_exit() then
      content.selected_index = nil

      parent:set_can_exit(false)
    end

    local selected_index = content.selected_index
    local value, new_value = nil
    local hotspot = content.hotspot
    local hotspot_style = style.hotspot

    if selected_index and focused then
      if using_gamepad and hotspot.on_pressed then
        new_value = options[selected_index].value
      end

      hotspot_style.on_pressed_sound = hotspot_style.on_pressed_fold_in_sound
    else
      hotspot_style.on_pressed_sound = hotspot_style.on_pressed_fold_out_sound
    end

    value = entry.get_function and entry:get_function() or content.internal_value or "<not selected>"

    if entry.controls_sub_widgets and content.dynamic_visibility_value ~= value then
      content.dynamic_visibility_value = value
      parent:cb_on_dynamic_setting_value_changed(widget, entry, value)
    end

    local preview_option = options_by_value[value]
    local preview_option_value = preview_option and preview_option.value
    local preview_value = preview_option and preview_option.display_name or Managers.localization:localize("loc_settings_option_unavailable")
    local preview_icon = preview_option and preview_option.icon
    local preview_icon_style = preview_option and preview_option.icon_style
    local has_preview_icon = not not preview_icon

    content.value_text = preview_value
    content.value_icon = preview_icon
    style.text.offset = has_preview_icon and style.text.icon_offset or style.text.default_offset

    if content.default_icon_styles and content.applied_preview_icon_style ~= preview_icon_style then
      apply_dropdown_icon_style(style.icon, content.default_icon_styles.value, preview_icon_style)
      content.applied_preview_icon_style = preview_icon_style
    end

    style.icon.visible = has_preview_icon

    local widget_type = widget.type
    local template = blueprints[widget_type]
    local size = template.size
    local scroll_amount = parent:settings_scroll_amount()
    local scroll_area_height = parent:settings_grid_length()
    local dropdown_length = size[2] * (num_visible_options + 1)
    local grow_downwards = true
    local always_keep_order = true

    if scroll_area_height <= offset[2] - scroll_amount + dropdown_length then
      grow_downwards = false
    end

    content.grow_downwards = grow_downwards
    local new_selection_index = nil

    if not selected_index or not focused then
      for i = 1, #options do
        local option = options[i]

        if option.value == preview_option_value then
          selected_index = i

          break
        end
      end

      selected_index = selected_index or 1
    end

    if selected_index and focused then
      if input_service:get("navigate_up_continuous") then
        if grow_downwards or not grow_downwards and always_keep_order then
          new_selection_index = math.max(selected_index - 1, 1)
        else
          new_selection_index = math.min(selected_index + 1, num_options)
        end
      elseif input_service:get("navigate_down_continuous") then
        if grow_downwards or not grow_downwards and always_keep_order then
          new_selection_index = math.min(selected_index + 1, num_options)
        else
          new_selection_index = math.max(selected_index - 1, 1)
        end
      end
    end

    if new_selection_index or not content.selected_index then
      if new_selection_index then
        selected_index = new_selection_index
      end

      if num_visible_options < num_options then
        local step_size = 1 / num_options
        local new_scroll_percentage = math.min(selected_index - 1, num_options) * step_size
        content.scroll_percentage = new_scroll_percentage
        content.scroll_add = nil
      end

      content.selected_index = selected_index
    end

    local scroll_percentage = content.scroll_percentage

    if scroll_percentage then
      local step_size = 1 / (num_options - (num_visible_options - 1))
      content.start_index = math.max(1, math.ceil(scroll_percentage / step_size))
    end

    local option_hovered = false
    local option_index = 1
    local start_index = content.start_index or 1
    local end_index = math.min(start_index + num_visible_options - 1, num_options)
    local using_scrollbar = num_visible_options < num_options

    for i = start_index, end_index do
      local actual_i = i

      if not grow_downwards and always_keep_order then
        actual_i = end_index - i + start_index
      end

      local option_text_id = "option_text_" .. option_index
      local option_icon_id = "option_icon_" .. option_index
      local option_hotspot_id = "option_hotspot_" .. option_index
      local outline_style_id = "outline_" .. option_index
      local option_hotspot = content[option_hotspot_id]
      option_hovered = option_hovered or option_hotspot.is_hover
      option_hotspot.is_selected = actual_i == selected_index
      local option = options[actual_i]

      if not new_value and focused and not using_gamepad and option_hotspot.on_pressed then
        option_hotspot.on_pressed = nil
        new_value = option.value
        content.selected_index = actual_i
      end

      local option_display_name = option.display_name
      local option_icon = option.icon
      local option_icon_style = option.icon_style
      local has_option_icon = not not option_icon

      content[option_icon_id] = option_icon
      content[option_text_id] = option_display_name
      local options_y = size[2] * option_index
      style[option_hotspot_id].offset[2] = grow_downwards and options_y or -options_y
      style[option_text_id].offset[2] = grow_downwards and options_y or -options_y

      if content.default_icon_styles
        and content.applied_option_icon_styles[option_index] ~= option_icon_style then
        apply_dropdown_icon_style(
          style[option_icon_id],
          content.default_icon_styles.options[option_index],
          option_icon_style
        )
        content.applied_option_icon_styles[option_index] = option_icon_style
      end

      style[option_icon_id].offset[2] = (grow_downwards and options_y or -options_y)
        + (option_icon_style and option_icon_style.offset and option_icon_style.offset[2] or 0)
      style[option_text_id].offset[1] = has_option_icon
        and style[option_text_id].icon_offset[1]
        or style[option_text_id].default_offset[1]
      style[option_icon_id].visible = has_option_icon
      local entry_length = using_scrollbar and settings_value_width - style.scrollbar_hotspot.size[1] or settings_value_width
      style[outline_style_id].size[1] = entry_length
      style[option_text_id].size[1] = settings_value_width
      option_index = option_index + 1
    end

    local value_changed = new_value ~= nil

    if value_changed then
      _last_dropdown_pressed = t
      if new_value ~= value then
        local on_activated = entry.on_activated
        on_activated(new_value, entry)
        entry.changed_callback(new_value)
      end
    end

    local scrollbar_hotspot = content.scrollbar_hotspot
    local scrollbar_hovered = scrollbar_hotspot.is_hover
    pass_input = using_gamepad or value_changed or not option_hovered and not scrollbar_hovered

    return pass_input
  end
}

blueprints.keybind = {
  size = {
    settings_grid_width,
    settings_value_height
  },
  pass_template = KeybindPassTemplates.settings_keybind(settings_grid_width, settings_value_height, settings_value_width),
  init = function (parent, widget, entry, callback_name, changed_callback_name)
    local content = widget.content
    local display_name = entry.display_name or parent:_localize("loc_settings_option_unavailable")
    content.text = display_name
    content.entry = entry
    content.key_unassigned_string = Managers.localization:localize("loc_keybind_unassigned")
  end,
  update = function (parent, widget, input_service, dt, t)
    local content = widget.content
    local entry = content.entry
    local value = entry:get_function()
    local preview_value = value and InputUtils.localized_string_from_key_info(value) or content.key_unassigned_string
    content.value_text = preview_value
    local hotspot = content.hotspot

    if hotspot.on_released then
      if (t - _last_dropdown_pressed) > _dropdown_deadzone then
        parent:show_keybind_popup(widget, entry, content.entry.cancel_keys)
      else
        _last_dropdown_pressed = -1
      end
    end
  end
}

blueprints.text = TextWidget.create_blueprint(settings_grid_width, settings_value_width, settings_value_height)
blueprints.text_input = TextInputWidget.create_blueprint(
  settings_grid_width,
  settings_value_width,
  settings_value_height
)

return settings("DMFOptionsViewContentBlueprints", blueprints)
