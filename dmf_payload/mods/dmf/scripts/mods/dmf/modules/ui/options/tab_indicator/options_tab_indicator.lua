local dmf = get_mod("DMF")

local OptionsTabIndicatorDefinitions = dmf:io_dofile(
  "dmf/scripts/mods/dmf/modules/ui/options/tab_indicator/options_tab_indicator_definitions"
)

local InputUtils = require("scripts/managers/input/input_utils")
local UIFonts = require("scripts/managers/ui/ui_fonts")
local UIRenderer = require("scripts/managers/ui/ui_renderer")

local SCREEN_WIDTH = OptionsTabIndicatorDefinitions.screen_width
local SCREEN_EDGE_PADDING = OptionsTabIndicatorDefinitions.screen_edge_padding
local TAB_WIDTH = OptionsTabIndicatorDefinitions.tab_width
local TAB_SPACING = OptionsTabIndicatorDefinitions.tab_spacing
local TAB_PITCH = TAB_WIDTH + TAB_SPACING
local PANEL_HORIZONTAL_PADDING = 80
local EDGE_FADE_WIDTH = TAB_PITCH * 4
local EDGE_MIN_ALPHA = 0
local SCROLL_DISTANCE = TAB_PITCH * 4
local SCROLL_SPEED = 12
local TOOLTIP_MAX_WIDTH = 600
local TOOLTIP_HORIZONTAL_PADDING = 20
local TOOLTIP_VERTICAL_PADDING = 12

local DEFAULT_COLOR = Color.terminal_frame(180, true)
local HOVER_COLOR = Color.terminal_frame_hover(255, true)
local ACTIVE_COLOR = Color.terminal_frame_selected(255, true)
local ACTIVE_HOVER_COLOR = Color.terminal_corner_selected(255, true)

local function set_color(target, source, alpha_multiplier)
  target[1] = source[1] * alpha_multiplier
  target[2] = source[2]
  target[3] = source[3]
  target[4] = source[4]
end

local function smoothstep(progress)
  return progress * progress * (3 - 2 * progress)
end

local ViewElementOptionsTabIndicator = class("ViewElementOptionsTabIndicator", "ViewElementBase")

ViewElementOptionsTabIndicator.init = function (self, parent, draw_layer, start_scale, context)
  local tabs = context.tabs
  local panel_width = context.available_width - PANEL_HORIZONTAL_PADDING
  local panel_x = context.available_x + PANEL_HORIZONTAL_PADDING * 0.5
  local definitions = OptionsTabIndicatorDefinitions.create(#tabs, panel_width, panel_x, context.panel_y)

  ViewElementOptionsTabIndicator.super.init(self, parent, draw_layer, start_scale, definitions)

  self._tabs = tabs
  self._panel_width = panel_width
  self._panel_x = panel_x
  self._active_index = 1
  self._get_focused_grid_index = context.get_focused_grid_index
  self._on_tab_pressed = context.on_tab_pressed
  self._get_scroll_amount = context.get_scroll_amount
  self._show_gamepad_prompts = context.show_gamepad_prompts
  self._content_width = #tabs * TAB_WIDTH + (#tabs - 1) * TAB_SPACING
  self._max_scroll_offset = math.max(self._content_width - panel_width, 0)
  self._scroll_offset = math.clamp(context.initial_scroll_offset or 0, 0, self._max_scroll_offset)
  self._target_scroll_offset = self._scroll_offset
  self._tab_widgets = {}
  self._focus_grid_indices = {}
  self._focus_tab_indices = {}
  self._scroll_tab_offsets = {}
  self._scroll_tab_indices = {}

  local previous_scroll_offset

  for i = 1, #tabs do
    local tab = tabs[i]

    self._tab_widgets[i] = self._widgets_by_name["tab_" .. i]

    if tab.focus_grid_index then
      self._focus_grid_indices[#self._focus_grid_indices + 1] = tab.focus_grid_index
      self._focus_tab_indices[#self._focus_tab_indices + 1] = i
    end

    if tab.scroll_offset ~= previous_scroll_offset then
      self._scroll_tab_offsets[#self._scroll_tab_offsets + 1] = tab.scroll_offset
      self._scroll_tab_indices[#self._scroll_tab_indices + 1] = i
      previous_scroll_offset = tab.scroll_offset
    end
  end

  self:_refresh_tabs()
end

ViewElementOptionsTabIndicator.horizontal_scroll_offset = function (self)
  return self._scroll_offset
end

ViewElementOptionsTabIndicator._select_tab = function (self, tab_index)
  local tab = self._tabs[tab_index]
  local active_index = tab_index

  while active_index > 1 and self._tabs[active_index - 1].scroll_offset == tab.scroll_offset do
    active_index = active_index - 1
  end

  self._target_tab_index = active_index
  self._active_index = active_index
  self:_ensure_tab_unfaded(tab_index)
  self._on_tab_pressed(tab)
end

ViewElementOptionsTabIndicator.relative_tab = function (self, direction, grid_index)
  local current_index = self:_tab_index_at_grid_index(grid_index) or self:_active_tab_index()

  local target_index = current_index + direction

  if target_index < 1 or target_index > #self._tabs then
    return
  end

  return self._tabs[target_index], target_index
end

ViewElementOptionsTabIndicator.select_focused_tab = function (self, tab_index)
  self._target_tab_index = nil
  self._active_index = tab_index
  self:_ensure_tab_unfaded(tab_index)
end

ViewElementOptionsTabIndicator._tab_index_at_grid_index = function (self, grid_index)
  if not grid_index then
    return
  end

  local indices = self._focus_grid_indices
  local low = 1
  local high = #indices
  local match = 0

  while low <= high do
    local middle = math.floor((low + high) * 0.5)

    if indices[middle] <= grid_index then
      match = middle
      low = middle + 1
    else
      high = middle - 1
    end
  end

  return match > 0 and self._focus_tab_indices[match] or 1
end

ViewElementOptionsTabIndicator._active_tab_index = function (self)
  local scroll_amount = self._get_scroll_amount() + 0.5
  local offsets = self._scroll_tab_offsets
  local low = 1
  local high = #offsets
  local match = 1

  while low <= high do
    local middle = math.floor((low + high) * 0.5)

    if offsets[middle] <= scroll_amount then
      match = middle
      low = middle + 1
    else
      high = middle - 1
    end
  end

  return self._scroll_tab_indices[match]
end

ViewElementOptionsTabIndicator._ensure_tab_unfaded = function (self, tab_index)
  local panel_width = self._panel_width
  local tab_start = (tab_index - 1) * TAB_PITCH
  local tab_end = tab_start + TAB_WIDTH
  local target_scroll_offset = self._target_scroll_offset

  if tab_start < target_scroll_offset + EDGE_FADE_WIDTH then
    target_scroll_offset = tab_start - EDGE_FADE_WIDTH
  elseif tab_end > target_scroll_offset + panel_width - EDGE_FADE_WIDTH then
    target_scroll_offset = tab_end + EDGE_FADE_WIDTH - panel_width
  end

  self._target_scroll_offset = math.clamp(target_scroll_offset, 0, self._max_scroll_offset)
end

ViewElementOptionsTabIndicator._edge_alpha = function (self, tab_center)
  local panel_width = self._panel_width
  local alpha = 1
  local left_hidden_distance = self._scroll_offset
  local right_hidden_distance = self._max_scroll_offset - self._scroll_offset

  if left_hidden_distance > 0 then
    local progress = math.clamp(tab_center / EDGE_FADE_WIDTH, 0, 1)
    local smooth_progress = smoothstep(progress)
    local faded_alpha = EDGE_MIN_ALPHA + (1 - EDGE_MIN_ALPHA) * smooth_progress
    local fade_strength = math.clamp(left_hidden_distance / EDGE_FADE_WIDTH, 0, 1)

    alpha = math.min(alpha, 1 - (1 - faded_alpha) * fade_strength)
  end

  if right_hidden_distance > 0 then
    local progress = math.clamp((panel_width - tab_center) / EDGE_FADE_WIDTH, 0, 1)
    local smooth_progress = smoothstep(progress)
    local faded_alpha = EDGE_MIN_ALPHA + (1 - EDGE_MIN_ALPHA) * smooth_progress
    local fade_strength = math.clamp(right_hidden_distance / EDGE_FADE_WIDTH, 0, 1)

    alpha = math.min(alpha, 1 - (1 - faded_alpha) * fade_strength)
  end

  return alpha
end

ViewElementOptionsTabIndicator._refresh_tabs = function (self)
  local panel_width = self._panel_width
  local centered_offset = self._max_scroll_offset == 0 and (panel_width - self._content_width) * 0.5 or 0
  local hovered_tab_index
  local pressed_tab_index

  for i = 1, #self._tabs do
    local widget = self._tab_widgets[i]
    local x = centered_offset + (i - 1) * TAB_PITCH - self._scroll_offset
    local tab_center = x + TAB_WIDTH * 0.5
    local visible = x + TAB_WIDTH >= 0 and x <= panel_width
    local interactable = tab_center >= 0 and tab_center <= panel_width
    local hotspot = widget.content.hotspot
    local hovered = interactable and hotspot.is_hover
    local active = i == self._active_index
    local color = active
      and (hovered and ACTIVE_HOVER_COLOR or ACTIVE_COLOR)
      or hovered and HOVER_COLOR
      or DEFAULT_COLOR
    local alpha = hovered and 1 or self:_edge_alpha(tab_center)

    widget.offset[1] = x
    widget.content.visible = visible
    widget.content.interactable = interactable
    hotspot.force_disabled = not interactable

    set_color(widget.style.frame.color, color, alpha)
    set_color(widget.style.fill.color, color, alpha * (active and 0.85 or 0.55))

    if self._using_cursor_navigation and hovered then
      hovered_tab_index = i

      if hotspot.on_pressed then
        pressed_tab_index = i
      end
    end
  end

  return hovered_tab_index, pressed_tab_index
end

ViewElementOptionsTabIndicator._update_tooltip = function (self, hovered_tab_index)
  local tooltip = self._widgets_by_name.tooltip

  if hovered_tab_index ~= self._hovered_tab_index then
    self._hovered_tab_index = hovered_tab_index
    self._tooltip_size_dirty = hovered_tab_index ~= nil
  end

  tooltip.content.text = hovered_tab_index and self._tabs[hovered_tab_index].display_name or ""
  tooltip.content.visible = hovered_tab_index ~= nil
end

ViewElementOptionsTabIndicator._update_scroll = function (self, dt, input_service)
  if self._using_cursor_navigation and self._widgets_by_name.panel.content.hotspot.is_hover then
    local scroll_axis = input_service:get("scroll_axis")
    local scroll = scroll_axis and scroll_axis[2] or 0

    if scroll ~= 0 then
      local direction = scroll > 0 and -1 or 1

      self._target_scroll_offset = math.clamp(
        self._target_scroll_offset + direction * SCROLL_DISTANCE,
        0,
        self._max_scroll_offset
      )
    end
  end

  local difference = self._target_scroll_offset - self._scroll_offset

  if math.abs(difference) < 0.1 then
    self._scroll_offset = self._target_scroll_offset
  else
    local interpolation = 1 - math.exp(-SCROLL_SPEED * dt)

    self._scroll_offset = self._scroll_offset + difference * interpolation
  end
end

ViewElementOptionsTabIndicator._update_gamepad_prompts = function (self)
  local visible = self._show_gamepad_prompts()
  local left_widget = self._widgets_by_name.input_left
  local right_widget = self._widgets_by_name.input_right

  left_widget.content.visible = visible
  right_widget.content.visible = visible

  if visible then
    local device_type = Managers.input:last_pressed_device():type()

    if self._gamepad_prompt_device_type == device_type then
      return
    end

    self._gamepad_prompt_device_type = device_type

    local service_type = "View"
    local left_alias = Managers.ui:get_input_alias_key("navigate_primary_left_pressed", service_type)
    local right_alias = Managers.ui:get_input_alias_key("navigate_primary_right_pressed", service_type)

    left_widget.content.text = InputUtils.input_text_for_current_input_device(service_type, left_alias)
    right_widget.content.text = InputUtils.input_text_for_current_input_device(service_type, right_alias)
  end
end

ViewElementOptionsTabIndicator.update = function (self, dt, t, input_service)
  ViewElementOptionsTabIndicator.super.update(self, dt, t, input_service)

  local using_cursor_navigation = self._using_cursor_navigation

  if not using_cursor_navigation then
    self._target_tab_index = nil
  end

  local scroll_active_index
  local target_tab_index = self._target_tab_index

  if target_tab_index and math.abs(self._get_scroll_amount() - self._tabs[target_tab_index].scroll_offset) >= 0.5 then
    scroll_active_index = target_tab_index
  else
    self._target_tab_index = nil
    scroll_active_index = self:_active_tab_index()
  end

  local focused_grid_index = not using_cursor_navigation and self._get_focused_grid_index()
  local active_index = self:_tab_index_at_grid_index(focused_grid_index) or scroll_active_index

  if active_index ~= self._active_index then
    self._active_index = active_index
    self:_ensure_tab_unfaded(active_index)
  end

  self:_update_scroll(dt, input_service)
  local hovered_tab_index, pressed_tab_index = self:_refresh_tabs()

  self:_update_tooltip(hovered_tab_index)
  self:_update_gamepad_prompts()

  if pressed_tab_index then
    self:_select_tab(pressed_tab_index)
  end
end

ViewElementOptionsTabIndicator._update_tooltip_layout = function (self, ui_renderer)
  local tooltip = self._widgets_by_name.tooltip
  local text_style = tooltip.style.text
  local font_options = UIFonts.get_font_options_by_style(text_style)
  local text_width, text_height = UIRenderer.text_size(
    ui_renderer,
    tooltip.content.text,
    text_style.font_type,
    text_style.font_size,
    { TOOLTIP_MAX_WIDTH, 0 },
    font_options
  )
  local width = math.ceil(text_width) + TOOLTIP_HORIZONTAL_PADDING
  local height = math.ceil(text_height) + TOOLTIP_VERTICAL_PADDING

  self:_set_scenegraph_size("tooltip", width, height)
  self:_force_update_scenegraph()

  self._tooltip_width = width
  self._tooltip_size_dirty = nil
end

ViewElementOptionsTabIndicator._draw_widgets = function (self, dt, t, input_service, ui_renderer, render_settings)
  local hovered_tab_index = self._hovered_tab_index

  if hovered_tab_index then
    if self._tooltip_size_dirty then
      self:_update_tooltip_layout(ui_renderer)
    end

    local hovered_widget = self._tab_widgets[hovered_tab_index]
    local tooltip = self._widgets_by_name.tooltip
    local tab_center = hovered_widget.offset[1] + TAB_WIDTH * 0.5
    local panel_left = self._panel_x
    local min_x = SCREEN_EDGE_PADDING - panel_left
    local max_x = SCREEN_WIDTH - SCREEN_EDGE_PADDING - panel_left - self._tooltip_width
    local tooltip_x = math.clamp(tab_center - self._tooltip_width * 0.5, min_x, max_x)

    tooltip.offset[1] = tooltip_x
  end

  ViewElementOptionsTabIndicator.super._draw_widgets(self, dt, t, input_service, ui_renderer, render_settings)
end

return ViewElementOptionsTabIndicator
