local dmf = get_mod("DMF")

local OptionsHeaderDefinitions = dmf:io_dofile(
  "dmf/scripts/mods/dmf/modules/ui/options/header/options_header_definitions"
)
local OptionsDisplayUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/options_display_utils")
local FilterInput = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/filter/filter_input")

local Text = require("scripts/utilities/ui/text")

local ELLIPSIS = "..."
local RESET_FORMAT = "{#reset()}"
local TEXT_FIT_PROBES = 16
local TEXT_MEASUREMENT_BOUND = 100000
local TOOLTIP_MAX_WIDTH = 600
local TOOLTIP_HORIZONTAL_PADDING = OptionsHeaderDefinitions.tooltip_horizontal_padding
local TOOLTIP_VERTICAL_PADDING = OptionsHeaderDefinitions.tooltip_vertical_padding
local TOOLTIP_TEXT_MARGIN = 2
local TOOLTIP_LINE_SPACING = 2
local TOOLTIP_GAP = 6
local TEXT_FORMAT_PATTERN = "{#[^}]+}"

local function normalize_single_line(text)
  return tostring(text or ""):gsub("[\r\n]+", " ")
end

local function line_width(ui_renderer, text, style)
  local width, _, _, caret = Text.text_size(ui_renderer, text, style, {
    TEXT_MEASUREMENT_BOUND,
    TEXT_MEASUREMENT_BOUND,
  }, true)

  return math.max(width, caret[1])
end

local function natural_text_width(ui_renderer, text, style)
  local normalized_text = tostring(text or ""):gsub("\r\n", "\n"):gsub("\r", "\n")
  local width = 0

  for line in string.gmatch(normalized_text .. "\n", "(.-)\n") do
    width = math.max(width, line_width(ui_renderer, line, style))
  end

  return width
end

local function text_fits(ui_renderer, text, style, max_width)
  local width = natural_text_width(ui_renderer, text, style)

  return math.ceil(width) <= max_width
end

local function visible_text_length(text)
  return Utf8.string_length(text:gsub(TEXT_FORMAT_PATTERN, ""))
end

local function visible_text_prefix(text, length)
  local parts = {}
  local byte_index = 1
  local remaining = length

  while byte_index <= #text do
    local format_start, format_end = string.find(text, TEXT_FORMAT_PATTERN, byte_index)
    local plain_end = format_start and format_start - 1 or #text

    if byte_index <= plain_end then
      local plain_text = string.sub(text, byte_index, plain_end)
      local plain_length = Utf8.string_length(plain_text)

      if remaining < plain_length then
        parts[#parts + 1] = remaining > 0 and Utf8.sub_string(plain_text, 1, remaining) or ""

        break
      end

      parts[#parts + 1] = plain_text
      remaining = remaining - plain_length
    end

    if not format_start or remaining == 0 then
      break
    end

    parts[#parts + 1] = string.sub(text, format_start, format_end)
    byte_index = format_end + 1
  end

  return table.concat(parts)
end

local function truncate_text(ui_renderer, text, style, max_width)
  local original_text = tostring(text or "")

  text = normalize_single_line(original_text)

  local display_changed = text ~= original_text

  if text_fits(ui_renderer, text, style, max_width) then
    return text, display_changed
  end

  local ellipsis = RESET_FORMAT .. ELLIPSIS

  if not text_fits(ui_renderer, ellipsis, style, max_width) then
    return "", true
  end

  local low = 0
  local high = visible_text_length(text)

  for _ = 1, TEXT_FIT_PROBES do
    local middle = math.ceil((low + high) * 0.5)
    local prefix = middle > 0 and visible_text_prefix(text, middle) or ""

    if text_fits(ui_renderer, prefix .. ellipsis, style, max_width) then
      low = middle
    else
      high = middle - 1
    end
  end

  local prefix = low > 0 and visible_text_prefix(text, low) or ""

  return prefix .. ellipsis, true
end

local ViewElementOptionsHeader = class("ViewElementOptionsHeader", "ViewElementBase")

ViewElementOptionsHeader.init = function (self, parent, draw_layer, start_scale, context)
  local definitions = OptionsHeaderDefinitions.create(context.panel_x, context.panel_y)

  ViewElementOptionsHeader.super.init(self, parent, draw_layer, start_scale, definitions)

  self._on_pin_changed = context.on_pin_changed
  self._on_toggle_changed = context.on_toggle_changed
  self._get_pin_value = context.get_pin_value
  self._get_toggle_value = context.get_toggle_value
  self._pin_tooltip_text = dmf:localize("mod_options_pin_tooltip")
  self._unpin_tooltip_text = dmf:localize("mod_options_unpin_tooltip")
  self._toggle_tooltip_text = dmf:localize("mod_options_toggle_tooltip")
  self._text_layout_dirty = true

  local toggle_content = self._widgets_by_name.toggle.content

  toggle_content.option_1 = Managers.localization:localize("loc_setting_checkbox_on")
  toggle_content.option_2 = Managers.localization:localize("loc_setting_checkbox_off")
end

ViewElementOptionsHeader.set_category = function (self, category_entry)
  self._category_entry = category_entry
  self._full_title = category_entry.display_name or ""
  self._full_description = category_entry.description or ""
  self._metadata = OptionsDisplayUtils.metadata_text(category_entry.version, category_entry.author)
  local mod_name = category_entry.mod_name

  self._title_tooltip_mod_name = not category_entry.is_toggle_mods_category and mod_name or nil
  self._has_pin = not category_entry.is_toggle_mods_category and mod_name ~= nil
  self._has_toggle = category_entry.is_togglable and not category_entry.is_toggle_mods_category or false
  local title_widget = self._widgets_by_name.title
  local pin_widget = self._widgets_by_name.pin
  local metadata_widget = self._widgets_by_name.metadata
  local description_widget = self._widgets_by_name.description
  local toggle_widget = self._widgets_by_name.toggle
  local filter_widget = self._widgets_by_name.filter
  local has_metadata = self._metadata ~= ""
  local has_description = self._full_description ~= ""
  local left_y = 0

  pin_widget.content.visible = self._has_pin

  self:_set_scenegraph_position(title_widget.scenegraph_id, nil, left_y)

  left_y = left_y + OptionsHeaderDefinitions.title_height
  metadata_widget.content.visible = has_metadata

  if has_metadata then
    self:_set_scenegraph_position(metadata_widget.scenegraph_id, nil, left_y)

    left_y = left_y + OptionsHeaderDefinitions.metadata_height
  end

  description_widget.content.visible = has_description

  if has_description then
    self:_set_scenegraph_position(description_widget.scenegraph_id, nil, left_y)

    left_y = left_y + OptionsHeaderDefinitions.description_height
  end

  local right_y = 0

  toggle_widget.content.visible = self._has_toggle

  if self._has_toggle then
    self:_set_scenegraph_position(toggle_widget.scenegraph_id, nil, right_y)

    right_y = right_y + OptionsHeaderDefinitions.control_height + OptionsHeaderDefinitions.control_spacing
  end

  self:_set_scenegraph_position(filter_widget.scenegraph_id, nil, right_y)

  right_y = right_y + OptionsHeaderDefinitions.control_height

  local panel_height = math.max(left_y, right_y)

  self:_set_scenegraph_size("panel", nil, panel_height)
  self:_force_update_scenegraph()
  self._text_layout_dirty = true
  self._hovered_tooltip_widget = nil
  self._tooltip_layout_dirty = nil
  self._widgets_by_name.tooltip.content.visible = false

  FilterInput.reset(filter_widget.content)

  self:set_focused_control(nil)

  return panel_height, OptionsHeaderDefinitions.panel_spacing
end

ViewElementOptionsHeader.filter_text = function (self)
  return self._widgets_by_name.filter.content.input_text or ""
end

ViewElementOptionsHeader.has_toggle = function (self)
  return self._has_toggle
end

ViewElementOptionsHeader.has_pin = function (self)
  return self._has_pin
end

ViewElementOptionsHeader.is_filter_writing = function (self)
  return self._widgets_by_name.filter.content.is_writing and true or false
end

ViewElementOptionsHeader.finish_filter_editing = function (self)
  FilterInput.finish_editing(self._widgets_by_name.filter.content)
end

ViewElementOptionsHeader.set_focused_control = function (self, control)
  if control == "toggle" and not self._has_toggle then
    control = nil
  elseif control == "pin" and not self._has_pin then
    control = nil
  end

  self._focused_control = control

  local toggle_hotspot = self._widgets_by_name.toggle.content.hotspot
  local pin_hotspot = self._widgets_by_name.pin.content.hotspot

  pin_hotspot.is_focused = control == "pin"
  toggle_hotspot.is_focused = control == "toggle"
  FilterInput.set_focused(self._widgets_by_name.filter.content, control == "filter")
end

ViewElementOptionsHeader.invalidate_text_layout = function (self)
  self._text_layout_dirty = true
end

ViewElementOptionsHeader._update_text_layout = function (self, ui_renderer)
  local title_widget = self._widgets_by_name.title
  local metadata_widget = self._widgets_by_name.metadata
  local description_widget = self._widgets_by_name.description
  local title_max_width = OptionsHeaderDefinitions.text_width
  local pin_widget = self._widgets_by_name.pin

  if self._has_pin then
    title_max_width = title_max_width - OptionsHeaderDefinitions.pin_size - OptionsHeaderDefinitions.pin_gap
  end

  local metadata_width = self:_scenegraph_size(metadata_widget.scenegraph_id)
  local description_width = self:_scenegraph_size(description_widget.scenegraph_id)
  local title_style = title_widget.style.text
  local metadata_style = metadata_widget.style.text
  local description_style = description_widget.style.text

  local title = truncate_text(ui_renderer, self._full_title, title_style, title_max_width)
  local metadata = truncate_text(ui_renderer, self._metadata, metadata_style, metadata_width)
  local description, description_differs = truncate_text(
    ui_renderer, self._full_description, description_style, description_width
  )

  title_widget.content.text = title
  title_widget.content.full_text = self._full_title
  title_widget.content.hotspot.force_disabled = self._title_tooltip_mod_name == nil
  metadata_widget.content.text = metadata
  description_widget.content.text = description
  description_widget.content.differs_from_full_text = description_differs
  description_widget.content.full_text = self._full_description
  description_widget.content.hotspot.force_disabled = not description_differs

  local title_width = math.min(math.ceil(line_width(ui_renderer, title, title_style)), title_max_width)

  self:_set_scenegraph_size(title_widget.scenegraph_id, title_width, nil)

  if self._has_pin then
    local pin_x = math.min(
      title_width + OptionsHeaderDefinitions.pin_gap,
      OptionsHeaderDefinitions.text_width - OptionsHeaderDefinitions.pin_size
    )

    self:_set_scenegraph_position(pin_widget.scenegraph_id, pin_x, nil)
  end

  self:_force_update_scenegraph()
  self._text_layout_dirty = nil
end

ViewElementOptionsHeader._update_pin = function (self)
  if not self._has_pin then
    return
  end

  local content = self._widgets_by_name.pin.content
  local value = self._get_pin_value(self._category_entry)

  content.is_pinned = value

  if content.hotspot.on_pressed then
    self._on_pin_changed(self._category_entry, not value)
  end
end

ViewElementOptionsHeader._update_toggle = function (self)
  local widget = self._widgets_by_name.toggle
  local content = widget.content

  if not self._has_toggle then
    return
  end

  local value = self._get_toggle_value(self._category_entry)
  local enabled_hotspot = content.option_hotspot_1
  local disabled_hotspot = content.option_hotspot_2

  enabled_hotspot.is_selected = value
  disabled_hotspot.is_selected = not value

  if content.hotspot.on_pressed then
    self._on_toggle_changed(self._category_entry, not value)
  end
end

ViewElementOptionsHeader._update_filter = function (self, input_service)
  local content = self._widgets_by_name.filter.content

  FilterInput.update(content, input_service, self._focused_control == "filter")
end

ViewElementOptionsHeader._position_tooltip = function (self, hovered_widget)
  local tooltip = self._widgets_by_name.tooltip
  local _, hovered_height = self:_scenegraph_size(hovered_widget.scenegraph_id)
  local hovered_position = self:scenegraph_position(hovered_widget.scenegraph_id)
  local widget_x = hovered_position[1] + hovered_widget.offset[1]
  local widget_y = hovered_position[2] + hovered_widget.offset[2]

  if hovered_widget == self._widgets_by_name.toggle then
    local panel_width = self:_scenegraph_size("panel")
    local tooltip_width = self:_scenegraph_size("tooltip")

    tooltip.offset[1] = panel_width + widget_x - tooltip_width
    tooltip.offset[2] = widget_y + hovered_height + TOOLTIP_GAP
  elseif hovered_widget == self._widgets_by_name.pin then
    local tooltip_width = self:_scenegraph_size("tooltip")
    local pin_width = self:_scenegraph_size(hovered_widget.scenegraph_id)

    tooltip.offset[1] = widget_x + (pin_width - tooltip_width) * 0.5
    tooltip.offset[2] = widget_y + hovered_height + TOOLTIP_GAP
  else
    local text_offset = hovered_widget.style.text.offset

    tooltip.offset[1] = widget_x + (text_offset and text_offset[1] or 0)
    tooltip.offset[2] = widget_y + hovered_height + TOOLTIP_GAP
  end
end

ViewElementOptionsHeader._update_tooltip = function (self)
  local hovered_widget
  local title_widget = self._widgets_by_name.title
  local description_widget = self._widgets_by_name.description
  local pin_widget = self._widgets_by_name.pin
  local toggle_widget = self._widgets_by_name.toggle
  local pin_hotspot = pin_widget.content.hotspot
  local toggle_hotspot = toggle_widget.content.hotspot

  if self._has_toggle and (toggle_hotspot.is_hover or toggle_hotspot.is_focused) then
    hovered_widget = toggle_widget
  elseif self._has_pin and (pin_hotspot.is_hover or pin_hotspot.is_focused) then
    hovered_widget = pin_widget
  elseif self._title_tooltip_mod_name and title_widget.content.hotspot.is_hover then
    hovered_widget = title_widget
  elseif description_widget.content.differs_from_full_text and description_widget.content.hotspot.is_hover then
    hovered_widget = description_widget
  end

  local tooltip = self._widgets_by_name.tooltip
  local tooltip_text

  if hovered_widget == toggle_widget then
    tooltip_text = self._toggle_tooltip_text
  elseif hovered_widget == pin_widget then
    tooltip_text = pin_widget.content.is_pinned and self._unpin_tooltip_text or self._pin_tooltip_text
  elseif hovered_widget then
    tooltip_text = hovered_widget.content.full_text
  end

  local mod_name_text = hovered_widget == title_widget and self._title_tooltip_mod_name or ""
  local tooltip_content_changed = hovered_widget and (
    tooltip.content.text ~= tooltip_text
    or tooltip.content.mod_name_text ~= mod_name_text
  )

  if hovered_widget ~= self._hovered_tooltip_widget or tooltip_content_changed then
    self._hovered_tooltip_widget = hovered_widget
    self._tooltip_layout_dirty = hovered_widget ~= nil
  end

  tooltip.content.visible = hovered_widget ~= nil

  if hovered_widget then
    tooltip.content.text = tooltip_text
    tooltip.content.mod_name_text = mod_name_text
    self:_position_tooltip(hovered_widget)
  end
end

ViewElementOptionsHeader._update_tooltip_layout = function (self, ui_renderer)
  local tooltip = self._widgets_by_name.tooltip
  local text_style = tooltip.style.text
  local mod_name_text_style = tooltip.style.mod_name_text
  local has_mod_name = tooltip.content.mod_name_text ~= ""
  local text_width = natural_text_width(ui_renderer, tooltip.content.text, text_style)
  local mod_name_width, mod_name_height = 0, 0

  if has_mod_name then
    mod_name_width = natural_text_width(ui_renderer, tooltip.content.mod_name_text, mod_name_text_style)
    mod_name_height = Text.text_height(ui_renderer, tooltip.content.mod_name_text, mod_name_text_style, {
      TOOLTIP_MAX_WIDTH,
      TEXT_MEASUREMENT_BOUND,
    }, true)
  end

  local content_width = math.min(
    math.ceil(math.max(text_width, mod_name_width)) + TOOLTIP_TEXT_MARGIN,
    TOOLTIP_MAX_WIDTH
  )
  local _, text_height = Text.text_size(ui_renderer, tooltip.content.text, text_style, {
    content_width,
    TEXT_MEASUREMENT_BOUND,
  }, true)
  local line_spacing = has_mod_name and TOOLTIP_LINE_SPACING or 0
  local horizontal_inset = TOOLTIP_HORIZONTAL_PADDING * 0.5
  local vertical_inset = TOOLTIP_VERTICAL_PADDING * 0.5
  local width = content_width + TOOLTIP_HORIZONTAL_PADDING
  local height = math.ceil(text_height) + math.ceil(mod_name_height) + line_spacing + TOOLTIP_VERTICAL_PADDING

  text_style.offset[1] = horizontal_inset
  text_style.offset[2] = vertical_inset
  text_style.size = { content_width, math.ceil(text_height) }
  mod_name_text_style.offset[1] = horizontal_inset
  mod_name_text_style.offset[2] = vertical_inset + math.ceil(text_height) + line_spacing
  mod_name_text_style.size = { content_width, math.ceil(mod_name_height) }

  self:_set_scenegraph_size("tooltip", width, height)
  self:_force_update_scenegraph()
  self:_position_tooltip(self._hovered_tooltip_widget)

  self._tooltip_layout_dirty = nil
end

ViewElementOptionsHeader.update = function (self, dt, t, input_service)
  if input_service:is_null_service() then
    self._hovered_tooltip_widget = nil
    self._tooltip_layout_dirty = nil
    self._widgets_by_name.tooltip.content.visible = false

    return ViewElementOptionsHeader.super.update(self, dt, t, input_service)
  end

  ViewElementOptionsHeader.super.update(self, dt, t, input_service)

  self:_update_pin()
  self:_update_toggle()
  self:_update_filter(input_service)
  self:_update_tooltip()
end

ViewElementOptionsHeader._draw_widgets = function (self, dt, t, input_service, ui_renderer, render_settings)
  if self._text_layout_dirty then
    self:_update_text_layout(ui_renderer)
  end

  if self._tooltip_layout_dirty then
    self:_update_tooltip_layout(ui_renderer)
  end

  ViewElementOptionsHeader.super._draw_widgets(self, dt, t, input_service, ui_renderer, render_settings)
end

return ViewElementOptionsHeader
