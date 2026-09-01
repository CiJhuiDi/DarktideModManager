local dmf = get_mod("DMF")

local _view_settings = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view_settings")
local FilterInput = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/filter/filter_input")
local OptionsDisplayUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/options_display_utils")

local CheckboxPassTemplates = require("scripts/ui/pass_templates/checkbox_pass_templates")
local UIFontSettings = require("scripts/managers/ui/ui_font_settings")
local UIWidget = require("scripts/managers/ui/ui_widget")
local UIWorkspaceSettings = require("scripts/settings/ui/ui_workspace_settings")

local PANEL_WIDTH = 1000
local PANEL_HEIGHT = _view_settings.settings_header_height
local CONTROL_WIDTH = 240
local CONTROL_HEIGHT = 44
local CONTROL_SPACING = 8
local COLUMN_SPACING = 40
local TEXT_WIDTH = PANEL_WIDTH - CONTROL_WIDTH - COLUMN_SPACING
local TITLE_HEIGHT = 60
local METADATA_HEIGHT = 30
local DESCRIPTION_HEIGHT = 40
local PIN_SIZE = 44
local PIN_GAP = 10
local PIN_FOCUS_PADDING = 4
local TOOLTIP_HORIZONTAL_PADDING = 20
local TOOLTIP_VERTICAL_PADDING = 12
local TOOLTIP_MOD_NAME_FONT_SIZE = 20

local title_text_style = table.clone(UIFontSettings.header_2)
title_text_style.text_horizontal_alignment = "left"
title_text_style.text_vertical_alignment = "bottom"

local description_text_style = table.clone(UIFontSettings.body_small)
description_text_style.text_horizontal_alignment = "left"
description_text_style.text_vertical_alignment = "center"
description_text_style.offset = { 0, 0, 3 }
description_text_style.hover_text_color = Color.ui_brown_super_light(255, true)

local metadata_text_style = table.clone(description_text_style)
metadata_text_style.text_color = Color.ui_grey_light(255, true)
metadata_text_style.hover_text_color = nil

local tooltip_text_style = table.clone(UIFontSettings.body)
tooltip_text_style.horizontal_alignment = "left"
tooltip_text_style.vertical_alignment = "top"
tooltip_text_style.text_horizontal_alignment = "left"
tooltip_text_style.text_vertical_alignment = "top"
tooltip_text_style.text_color = Color.white(255, true)
tooltip_text_style.offset = { 0, 0, 2 }

local tooltip_mod_name_text_style = table.clone(tooltip_text_style)
tooltip_mod_name_text_style.font_size = TOOLTIP_MOD_NAME_FONT_SIZE
tooltip_mod_name_text_style.text_color = Color.ui_grey_medium(255, true)

local pin_text_style = table.clone(UIFontSettings.header_3)
pin_text_style.text_horizontal_alignment = "center"
pin_text_style.text_vertical_alignment = "center"
pin_text_style.text_color = Color.ui_grey_light(255, true)

local PINNED_COLOR = { 255, 226, 199, 126 }
local PINNED_HOVER_COLOR = Color.ui_brown_super_light(255, true)
local UNPINNED_COLOR = Color.ui_grey_light(255, true)
local UNPINNED_HOVER_COLOR = Color.terminal_text_header_selected(255, true)

local function copy_color(target, source)
  for i = 1, 4 do
    target[i] = source[i]
  end
end

local OptionsHeaderDefinitions = {}

OptionsHeaderDefinitions.panel_spacing = _view_settings.settings_header_spacing
OptionsHeaderDefinitions.tooltip_horizontal_padding = TOOLTIP_HORIZONTAL_PADDING
OptionsHeaderDefinitions.tooltip_vertical_padding = TOOLTIP_VERTICAL_PADDING
OptionsHeaderDefinitions.title_height = TITLE_HEIGHT
OptionsHeaderDefinitions.metadata_height = METADATA_HEIGHT
OptionsHeaderDefinitions.description_height = DESCRIPTION_HEIGHT
OptionsHeaderDefinitions.control_height = CONTROL_HEIGHT
OptionsHeaderDefinitions.control_spacing = CONTROL_SPACING
OptionsHeaderDefinitions.text_width = TEXT_WIDTH
OptionsHeaderDefinitions.pin_size = PIN_SIZE
OptionsHeaderDefinitions.pin_gap = PIN_GAP

OptionsHeaderDefinitions.create = function (panel_x, panel_y)
  local scenegraph_definition = {
    screen = UIWorkspaceSettings.screen,
    panel = {
      parent = "screen",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { PANEL_WIDTH, PANEL_HEIGHT },
      position = { panel_x, panel_y, 1 },
    },
    title = {
      parent = "panel",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { TEXT_WIDTH, TITLE_HEIGHT },
      position = { 0, 0, 1 },
    },
    pin = {
      parent = "panel",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { PIN_SIZE, PIN_SIZE },
      position = { 0, TITLE_HEIGHT - PIN_SIZE, 2 },
    },
    metadata = {
      parent = "panel",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { TEXT_WIDTH, METADATA_HEIGHT },
      position = { 0, TITLE_HEIGHT, 1 },
    },
    description = {
      parent = "panel",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { TEXT_WIDTH, DESCRIPTION_HEIGHT },
      position = { 0, TITLE_HEIGHT + METADATA_HEIGHT, 1 },
    },
    toggle = {
      parent = "panel",
      horizontal_alignment = "right",
      vertical_alignment = "top",
      size = { CONTROL_WIDTH, CONTROL_HEIGHT },
      position = { 0, 0, 1 },
    },
    filter = {
      parent = "panel",
      horizontal_alignment = "right",
      vertical_alignment = "top",
      size = { CONTROL_WIDTH, CONTROL_HEIGHT },
      position = { 0, CONTROL_HEIGHT + CONTROL_SPACING, 1 },
    },
    tooltip = {
      parent = "panel",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { 0, 0 },
      position = { 0, 0, 20 },
    },
  }
  local widget_definitions = {
    title = UIWidget.create_definition({
      {
        pass_type = "hotspot",
        content_id = "hotspot",
      },
      {
        pass_type = "text",
        value = "",
        value_id = "text",
        style = title_text_style,
        style_id = "text",
      },
    }, "title"),
    pin = UIWidget.create_definition({
      {
        pass_type = "hotspot",
        content_id = "hotspot",
        content = {
          use_is_focused = true,
        },
      },
      {
        pass_type = "text",
        value = OptionsDisplayUtils.pin_symbol,
        style = pin_text_style,
        change_function = function (content, style)
          local hotspot = content.hotspot
          local highlighted = hotspot.is_hover or hotspot.is_focused
          local color = content.is_pinned
            and (highlighted and PINNED_HOVER_COLOR or PINNED_COLOR)
            or (highlighted and UNPINNED_HOVER_COLOR or UNPINNED_COLOR)

          copy_color(style.text_color, color)
        end,
      },
      {
        pass_type = "texture",
        value = "content/ui/materials/frames/frame_corner_2px",
        style = {
          color = Color.terminal_corner_hover_bright(255, true),
          offset = { -PIN_FOCUS_PADDING, -PIN_FOCUS_PADDING, 2 },
          size_addition = { PIN_FOCUS_PADDING * 2, PIN_FOCUS_PADDING * 2 },
          scale_to_material = true,
        },
        visibility_function = function (content)
          return content.hotspot.is_focused
        end,
      },
    }, "pin", {
      visible = false,
      is_pinned = false,
    }),
    metadata = UIWidget.create_definition({
      {
        pass_type = "text",
        value = "",
        value_id = "text",
        style = metadata_text_style,
        style_id = "text",
      },
    }, "metadata"),
    description = UIWidget.create_definition({
      {
        pass_type = "hotspot",
        content_id = "hotspot",
      },
      {
        pass_type = "text",
        value = "",
        value_id = "text",
        style = description_text_style,
        style_id = "text",
      },
    }, "description"),
    toggle = UIWidget.create_definition(
      CheckboxPassTemplates.settings_checkbox(CONTROL_WIDTH, CONTROL_HEIGHT, CONTROL_WIDTH, 2, true),
      "toggle",
      { visible = false }
    ),
    filter = UIWidget.create_definition(FilterInput.create_passes(), "filter", {
      input_text = "",
      placeholder_text = " \u{e04a}",
    }),
    tooltip = UIWidget.create_definition({
      {
        pass_type = "rect",
        style = {
          horizontal_alignment = "center",
          vertical_alignment = "center",
          color = Color.ui_terminal(255, true),
          offset = { 0, 0, 0 },
        },
      },
      {
        pass_type = "rect",
        style = {
          horizontal_alignment = "center",
          vertical_alignment = "center",
          color = Color.black(255, true),
          offset = { 0, 0, 1 },
          size_addition = { -3, -3 },
        },
      },
      {
        pass_type = "text",
        value = "",
        value_id = "text",
        style = tooltip_text_style,
        style_id = "text",
      },
      {
        pass_type = "text",
        value = "",
        value_id = "mod_name_text",
        style = tooltip_mod_name_text_style,
        style_id = "mod_name_text",
      },
    }, "tooltip", {
      visible = false,
    }),
  }

  return {
    scenegraph_definition = scenegraph_definition,
    widget_definitions = widget_definitions,
  }
end

return OptionsHeaderDefinitions
