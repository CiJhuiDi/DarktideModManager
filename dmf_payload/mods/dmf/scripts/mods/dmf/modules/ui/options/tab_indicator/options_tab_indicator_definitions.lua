local dmf = get_mod("DMF")

local _view_settings = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view_settings")

local UIFontSettings = require("scripts/managers/ui/ui_font_settings")
local UIWidget = require("scripts/managers/ui/ui_widget")
local UIWorkspaceSettings = require("scripts/settings/ui/ui_workspace_settings")

local PANEL_HEIGHT = _view_settings.settings_tab_height
local SCREEN_WIDTH = 1920
local SCREEN_EDGE_PADDING = 20
local TAB_WIDTH = 32
local TAB_HEIGHT = 8
local TAB_HOTSPOT_HEIGHT = 34
local TAB_SPACING = 7

local OptionsTabIndicatorDefinitions = {
  screen_edge_padding = SCREEN_EDGE_PADDING,
  screen_width = SCREEN_WIDTH,
  tab_spacing = TAB_SPACING,
  tab_width = TAB_WIDTH,
}

OptionsTabIndicatorDefinitions.create = function (num_tabs, panel_width, panel_x, panel_y)
  local scenegraph_definition = {
    screen = UIWorkspaceSettings.screen,
    panel = {
      parent = "screen",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { panel_width, PANEL_HEIGHT },
      position = { panel_x, panel_y, 1 },
    },
    tooltip = {
      parent = "panel",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { 0, 0 },
      position = { 0, PANEL_HEIGHT + 6, 10 },
    },
    input_left = {
      parent = "panel",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { 40, PANEL_HEIGHT },
      position = { -52, 0, 3 },
    },
    input_right = {
      parent = "panel",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { 40, PANEL_HEIGHT },
      position = { panel_width + 12, 0, 3 },
    },
  }
  local widget_definitions = {
    panel = UIWidget.create_definition({
      {
        pass_type = "hotspot",
        content_id = "hotspot",
      },
    }, "panel"),
  }
  local tooltip_text_style = table.clone(UIFontSettings.body)
  local input_text_style = table.clone(UIFontSettings.body)

  input_text_style.font_size = 28
  input_text_style.text_horizontal_alignment = "center"
  input_text_style.text_vertical_alignment = "center"
  input_text_style.text_color = Color.terminal_text_header(255, true)
  input_text_style.offset = { 0, 0, 2 }

  tooltip_text_style.text_horizontal_alignment = "center"
  tooltip_text_style.text_vertical_alignment = "center"
  tooltip_text_style.text_color = Color.white(255, true)
  tooltip_text_style.offset = { 0, 0, 2 }

  widget_definitions.tooltip = UIWidget.create_definition({
    {
      pass_type = "rect",
      style_id = "frame",
      style = {
        horizontal_alignment = "center",
        vertical_alignment = "center",
        color = Color.ui_terminal(255, true),
        offset = { 0, 0, 0 },
      },
    },
    {
      pass_type = "rect",
      style_id = "background",
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
      style_id = "text",
      style = tooltip_text_style,
    },
  }, "tooltip", {
    visible = false,
  })
  widget_definitions.input_left = UIWidget.create_definition({
    {
      pass_type = "text",
      value = "",
      value_id = "text",
      style = table.clone(input_text_style),
    },
  }, "input_left", {
    visible = false,
  })
  widget_definitions.input_right = UIWidget.create_definition({
    {
      pass_type = "text",
      value = "",
      value_id = "text",
      style = table.clone(input_text_style),
    },
  }, "input_right", {
    visible = false,
  })

  for i = 1, num_tabs do
    local scenegraph_id = "tab_" .. i

    scenegraph_definition[scenegraph_id] = {
      parent = "panel",
      horizontal_alignment = "left",
      vertical_alignment = "top",
      size = { TAB_WIDTH, TAB_HOTSPOT_HEIGHT },
      position = { 0, 3, 2 },
    }
    widget_definitions[scenegraph_id] = UIWidget.create_definition({
      {
        pass_type = "hotspot",
        content_id = "hotspot",
      },
      {
        pass_type = "rect",
        style_id = "frame",
        style = {
          color = Color.terminal_frame(180, true),
          offset = { 0, (TAB_HOTSPOT_HEIGHT - TAB_HEIGHT) * 0.5, 1 },
          size = { TAB_WIDTH, TAB_HEIGHT },
        },
      },
      {
        pass_type = "rect",
        style_id = "fill",
        style = {
          color = Color.ui_terminal(180, true),
          offset = { 2, (TAB_HOTSPOT_HEIGHT - TAB_HEIGHT) * 0.5 + 2, 2 },
          size = { TAB_WIDTH - 4, TAB_HEIGHT - 4 },
        },
      },
    }, scenegraph_id)
  end

  return {
    scenegraph_definition = scenegraph_definition,
    widget_definitions = widget_definitions,
  }
end

return OptionsTabIndicatorDefinitions
