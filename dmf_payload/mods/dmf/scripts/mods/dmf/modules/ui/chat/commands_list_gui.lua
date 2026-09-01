---@class DMFMod
local dmf = get_mod("DMF")

local Text = require("scripts/utilities/ui/text")
local UIRenderer = require("scripts/managers/ui/ui_renderer")

local FONT_TYPE = "proxima_nova_bold"
local FONT_SIZE = 22

local MAX_COMMANDS_VISIBLE = 5

local STRING_HEIGHT   = 25
local STRING_Y_OFFSET = 2
local STRING_X_MARGIN = 10

local COUNT_PADDING_X = 6
local COUNT_PADDING_Y = 3

local PANEL_SPACING = 5
local MAX_PANEL_WIDTH = 1000
local OFFSET_Z = 880
local TEXT_MEASUREMENT_BOUND = 100000

local COMMAND_COLOR_FORMAT = "{#color(100,255,100)}"
local RESET_FORMAT = "{#reset()}"

local PANEL_COLOR = { 200, 10, 10, 10 }
local SELECTION_COLOR = { 100, 120, 120, 120 }
local TEXT_COLOR = { 255, 255, 255, 255 }
local COUNT_TEXT_COLOR = { 255, 200, 200, 200 }
local COUNT_BACKGROUND_COLOR = { 220, 0, 0, 0 }

local TEXT_STYLE = {
  font_type = FONT_TYPE,
  font_size = FONT_SIZE,
  text_horizontal_alignment = "left",
  text_vertical_alignment = "top",
}

local TEXT_OPTIONS = {
  horizontal_alignment = Gui.HorizontalAlignLeft,
  vertical_alignment = Gui.VerticalAlignTop,
}

-- #####################################################################################################################
-- ##### Local functions ###############################################################################################
-- #####################################################################################################################

local function get_panel_layout(chat_element, ui_renderer)
  local chat_window_position = chat_element:scenegraph_world_position("chat_window")
  local chat_window_size = chat_element:scenegraph_size("chat_window")
  local screen_position = chat_element:scenegraph_world_position("screen")
  local screen_size = chat_element:scenegraph_size("screen", ui_renderer.scale)
  local panel_x = chat_window_position[1]
  local panel_bottom = chat_window_position[2] - PANEL_SPACING
  local available_width = screen_position[1] + screen_size[1] - panel_x
  local maximum_width = math.max(chat_window_size[1], math.min(MAX_PANEL_WIDTH, available_width))

  return panel_x, panel_bottom, chat_window_size[1], maximum_width
end

local function text_size(ui_renderer, text, width)
  local scale = ui_renderer.scale
  local text_width, text_height, _, caret = Text.text_size(ui_renderer, text, TEXT_STYLE, {
    width * scale,
    TEXT_MEASUREMENT_BOUND * scale,
  }, true)

  return math.max(text_width, caret[1]) / scale, text_height / scale
end


local function format_command(command)
  local text = COMMAND_COLOR_FORMAT .. "/" .. command.name .. RESET_FORMAT

  if command.description ~= "" then
    text = text .. " " .. command.description
  end

  return text .. RESET_FORMAT
end


local function draw_count(ui_renderer, text, panel_x, panel_top)
  local text_width, text_height = text_size(ui_renderer, text, TEXT_MEASUREMENT_BOUND)
  local content_width = math.ceil(text_width)
  local content_height = math.ceil(text_height)
  local background_width = content_width + COUNT_PADDING_X * 2
  local background_height = content_height + COUNT_PADDING_Y * 2
  local background_y = panel_top - background_height

  UIRenderer.draw_rect(
    ui_renderer,
    Vector3(panel_x, background_y, OFFSET_Z),
    Vector2(background_width, background_height),
    COUNT_BACKGROUND_COLOR
  )
  UIRenderer.draw_text(
    ui_renderer,
    text,
    FONT_SIZE,
    FONT_TYPE,
    Vector3(panel_x + COUNT_PADDING_X, background_y + COUNT_PADDING_Y, OFFSET_Z + 2),
    Vector2(content_width, content_height),
    COUNT_TEXT_COLOR,
    TEXT_OPTIONS
  )
end


local function draw(chat_element, commands_list, selected_command_index, ui_renderer)
  if not ui_renderer or not ui_renderer.gui then
    return
  end

  TEXT_STYLE.font_type = FONT_TYPE
  TEXT_STYLE.font_size = FONT_SIZE

  -- pick displayed commands
  local last_displayed_command = math.max(math.min(MAX_COMMANDS_VISIBLE, #commands_list), selected_command_index)
  local first_displayed_command = math.max(1, last_displayed_command - (MAX_COMMANDS_VISIBLE - 1))
  local displayed_commands = {}
  for i = first_displayed_command, last_displayed_command do
    local command = commands_list[i]

    displayed_commands[#displayed_commands + 1] = {
      selected = i == selected_command_index,
      text = format_command(command),
    }
  end

  local panel_x, panel_bottom, minimum_width, maximum_width = get_panel_layout(chat_element, ui_renderer)
  local maximum_text_width = maximum_width - STRING_X_MARGIN * 2
  local panel_text_width = minimum_width - STRING_X_MARGIN * 2

  for i = 1, #displayed_commands do
    local command = displayed_commands[i]
    local command_width, command_height = text_size(ui_renderer, command.text, TEXT_MEASUREMENT_BOUND)

    if command_width > maximum_text_width then
      command_width, command_height = text_size(ui_renderer, command.text, maximum_text_width)
    end

    command.text_height = math.ceil(command_height)
    panel_text_width = math.max(panel_text_width, math.ceil(command_width))
  end

  local panel_width = math.min(maximum_width, panel_text_width + STRING_X_MARGIN * 2)
  local text_width = panel_width - STRING_X_MARGIN * 2
  local panel_top = panel_bottom

  for i = 1, #displayed_commands do
    local command = displayed_commands[i]

    command.height = math.max(STRING_HEIGHT, command.text_height + STRING_Y_OFFSET * 2)
    panel_top = panel_top - command.height
    command.y = panel_top
  end

  local panel_height = panel_bottom - panel_top

  UIRenderer.draw_rect(
    ui_renderer,
    Vector3(panel_x, panel_top, OFFSET_Z),
    Vector2(panel_width, panel_height),
    PANEL_COLOR
  )

  for i = 1, #displayed_commands do
    local command = displayed_commands[i]

    if command.selected then
      UIRenderer.draw_rect(
        ui_renderer,
        Vector3(panel_x, command.y, OFFSET_Z + 1),
        Vector2(panel_width, command.height),
        SELECTION_COLOR
      )
    end

    UIRenderer.draw_text(
      ui_renderer,
      command.text,
      FONT_SIZE,
      FONT_TYPE,
      Vector3(panel_x + STRING_X_MARGIN, command.y + STRING_Y_OFFSET, OFFSET_Z + 2),
      Vector2(text_width, command.text_height),
      TEXT_COLOR,
      TEXT_OPTIONS
    )
  end

  -- "selected command number / total commands number" indicator
  if not ((#commands_list == 1) and (selected_command_index > 0)) then
    local total_number_indicator = tostring(#commands_list)
    if selected_command_index > 0 then
      total_number_indicator = selected_command_index .. "/" .. total_number_indicator
    end

    draw_count(ui_renderer, total_number_indicator, panel_x, panel_top)
  end
end

-- #####################################################################################################################
-- ##### DMF internal functions ########################################################################################
-- #####################################################################################################################

-- A way for modders to change definitions. No safety checks. No guarantees definitions won't change. At least until
-- global refactoring.
function dmf.update_commands_list_gui_definitions(new_definitions)
  FONT_TYPE                  = new_definitions.FONT_TYPE                  or FONT_TYPE
  FONT_SIZE                  = new_definitions.FONT_SIZE                  or FONT_SIZE
  MAX_COMMANDS_VISIBLE       = new_definitions.MAX_COMMANDS_VISIBLE       or MAX_COMMANDS_VISIBLE
  STRING_HEIGHT              = new_definitions.STRING_HEIGHT              or STRING_HEIGHT
  STRING_Y_OFFSET            = new_definitions.STRING_Y_OFFSET            or STRING_Y_OFFSET
  STRING_X_MARGIN            = new_definitions.STRING_X_MARGIN            or STRING_X_MARGIN
  OFFSET_Z                   = new_definitions.OFFSET_Z                   or OFFSET_Z
end

-- #####################################################################################################################
-- ##### Return ########################################################################################################
-- #####################################################################################################################

return { draw = draw }
