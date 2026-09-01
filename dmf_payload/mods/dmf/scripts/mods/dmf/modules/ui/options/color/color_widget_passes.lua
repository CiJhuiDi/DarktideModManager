local ListHeaderPassTemplates = require("scripts/ui/pass_templates/list_header_templates")
local UIFontSettings = require("scripts/managers/ui/ui_font_settings")
local UIResolution = require("scripts/managers/ui/ui_resolution")

local PREVIEW_SIZE = 64
local PREVIEW_GAP = 8
local CHANNEL_LABEL_WIDTH = 20
local MAX_TRACK_HEIGHT = 16
local TRACK_COLOR = Color.terminal_corner(140, true)
local TRACK_HOVER_COLOR = Color.terminal_corner_hover(165, true)
local HIGHLIGHT_SIZE_ADDITION = ListHeaderPassTemplates.highlight_size_addition

local CHANNELS = {
  { index = 1, label = "A" },
  { index = 2, label = "R" },
  { index = 3, label = "G" },
  { index = 4, label = "B" },
}

local function cursor_x(input_service, inverse_scale)
  local cursor = UIResolution.inverse_scale_vector(input_service:get("cursor"), inverse_scale)

  return cursor[1]
end

local function track_geometry(controls_x, controls_width)
  return controls_x + CHANNEL_LABEL_WIDTH, controls_width - CHANNEL_LABEL_WIDTH
end

local function stop_drag(content)
  content.active_color_channel = nil
  content.drag_active = nil
end

local function preview_is_highlighted(content)
  return content.preview_hotspot.is_hover
    or content.exclusive_focus and content.gamepad_selected_control == "preview"
end

local function create_drag_logic(channels, has_alpha, controls_x, controls_width)
  local track_x, track_width = track_geometry(controls_x, controls_width)

  return function (pass_, renderer, style_, content, position)
    local input_service = renderer.input_service

    if not input_service then
      return
    end

    if content.disabled then
      stop_drag(content)

      return
    end

    local active_channel = content.active_color_channel

    if not active_channel then
      for i = 1, #channels do
        local channel = channels[i]
        local hotspot = content["color_hotspot_" .. channel.index]

        if hotspot.on_pressed then
          active_channel = channel.index
          content.active_color_channel = active_channel
          content.drag_active = true

          break
        end
      end

      if not active_channel then
        return
      end
    end

    if not input_service:get("left_hold") then
      stop_drag(content)

      return
    end

    local current_cursor_x = cursor_x(input_service, renderer.inverse_scale)
    local track_progress = math.clamp((current_cursor_x - position[1] - track_x) / track_width, 0, 1)
    local component_value = math.round(track_progress * 255)

    if content.preview_color[active_channel] == component_value then
      return
    end

    content.preview_color[active_channel] = component_value

    if not has_alpha then
      content.preview_color[1] = 255
    end

    content.on_color_changed()
  end
end

local function create_checkerboard_passes(preview_x)
  local passes = {
    {
      pass_type = "rect",
      style_id = "color_checkerboard_background",
      style = {
        color = { 255, 255, 255, 255 },
        offset = { preview_x, 0, 2 },
        size = { PREVIEW_SIZE, PREVIEW_SIZE },
      },
    },
  }
  local tile_size = PREVIEW_SIZE / 4

  for row = 0, 3 do
    for column = 0, 3 do
      if (row + column) % 2 == 0 then
        passes[#passes + 1] = {
          pass_type = "rect",
          style_id = string.format("color_checkerboard_%d_%d", row, column),
          style = {
            color = { 255, 204, 204, 204 },
            offset = { preview_x + column * tile_size, row * tile_size, 3 },
            size = { tile_size, tile_size },
          },
        }
      end
    end
  end

  return passes
end

local function create_preview_passes(preview_x)
  local passes = create_checkerboard_passes(preview_x)
  local edit_text_style = table.clone(UIFontSettings.list_button)

  edit_text_style.font_size = 40
  edit_text_style.offset = { preview_x, 0, 6 }
  edit_text_style.size = { PREVIEW_SIZE, PREVIEW_SIZE }
  edit_text_style.text_color = Color.terminal_text_header(180, true)
  edit_text_style.text_horizontal_alignment = "center"
  edit_text_style.text_vertical_alignment = "center"

  passes[#passes + 1] = {
    pass_type = "rect",
    style_id = "color_preview",
    style = {
      color = Color.white(255, true),
      offset = { preview_x, 0, 4 },
      size = { PREVIEW_SIZE, PREVIEW_SIZE },
    },
    change_function = function (content, style)
      local preview_color = content.preview_color
      local color = style.color

      for i = 1, 4 do
        color[i] = preview_color[i]
      end
    end,
  }
  passes[#passes + 1] = {
    pass_type = "texture",
    value = "content/ui/materials/frames/frame_corner_2px",
    style = {
      color = Color.terminal_corner_hover(255, true),
      offset = { preview_x, 0, 10 },
      size = { PREVIEW_SIZE, PREVIEW_SIZE },
      scale_to_material = true,
    },
    visibility_function = function (content)
      return content.exclusive_focus and content.gamepad_selected_control == "preview"
    end,
  }
  passes[#passes + 1] = {
    content_id = "preview_hotspot",
    pass_type = "hotspot",
    style = {
      offset = { preview_x, 0, 9 },
      size = { PREVIEW_SIZE, PREVIEW_SIZE },
    },
  }
  passes[#passes + 1] = {
    pass_type = "rect",
    style_id = "color_preview_hover_overlay",
    style = {
      color = Color.black(128, true),
      offset = { preview_x, 0, 5 },
      size = { PREVIEW_SIZE, PREVIEW_SIZE },
    },
    visibility_function = function (content)
      return not content.disabled and preview_is_highlighted(content)
    end,
  }
  passes[#passes + 1] = {
    pass_type = "text",
    style_id = "color_preview_edit_text",
    value = "\u{e029}",
    style = edit_text_style,
    visibility_function = function (content)
      return not content.disabled and preview_is_highlighted(content)
    end,
  }
  passes[#passes + 1] = {
    pass_type = "texture",
    style_id = "color_preview_frame",
    value = "content/ui/materials/frames/frame_tile_2px",
    style = {
      color = Color.terminal_frame(255, true),
      offset = { preview_x, 0, 7 },
      size = { PREVIEW_SIZE, PREVIEW_SIZE },
    },
  }

  return passes
end

local function create_channel_passes(channel, channel_order, channel_count, controls_x, controls_width, height)
  local channel_index = channel.index
  local row_height = math.floor(height / channel_count)
  local row_y = (height - row_height * channel_count) * 0.5 + (channel_order - 1) * row_height
  local track_height = math.min(MAX_TRACK_HEIGHT, row_height - 4)
  local track_y = row_y + (row_height - track_height) * 0.5
  local track_x, track_width = track_geometry(controls_x, controls_width)
  local hotspot_id = "color_hotspot_" .. channel_index
  local value_id = "color_value_" .. channel_index
  local label_style = table.clone(UIFontSettings.list_button)
  local value_style = table.clone(UIFontSettings.list_button)

  label_style.font_size = 14
  label_style.offset = { controls_x, row_y, 6 }
  label_style.size = { CHANNEL_LABEL_WIDTH, row_height }
  label_style.text_color = Color.terminal_text_body(255, true)
  label_style.text_horizontal_alignment = "center"
  label_style.text_vertical_alignment = "center"

  value_style.font_size = 14
  value_style.offset = { track_x, row_y, 8 }
  value_style.size = { track_width, row_height }
  value_style.text_color = Color.terminal_text_header(255, true)
  value_style.text_horizontal_alignment = "center"
  value_style.text_vertical_alignment = "center"

  return {
    {
      pass_type = "text",
      style_id = "color_label_" .. channel_index,
      value = channel.label,
      style = label_style,
    },
    {
      pass_type = "texture",
      style_id = "color_track_background_" .. channel_index,
      value = "content/ui/materials/buttons/background_selected",
      style = {
        color = Color.terminal_text_body_dark(255, true),
        offset = { track_x, track_y, 2 },
        size = { track_width, track_height },
      },
    },
    {
      pass_type = "texture",
      style_id = "color_track_fill_" .. channel_index,
      value = "content/ui/materials/buttons/background_selected_edge",
      style = {
        color = table.clone(TRACK_COLOR),
        offset = { track_x, track_y, 3 },
        size = { track_width, track_height },
      },
      change_function = function (content, style)
        style.size[1] = track_width * content.preview_color[channel_index] / 255

        local hotspot = content[hotspot_id]
        local highlighted = content.active_color_channel == channel_index
          or content.gamepad_active_channel == channel_index
          or hotspot.is_hover
        local target_color = highlighted and TRACK_HOVER_COLOR or TRACK_COLOR

        for i = 1, 4 do
          style.color[i] = target_color[i]
        end
      end,
    },
    {
      content_id = hotspot_id,
      pass_type = "hotspot",
      style_id = hotspot_id,
      style = {
        offset = { track_x, row_y, 7 },
        size = { track_width, row_height },
      },
    },
    {
      pass_type = "texture",
      value = "content/ui/materials/frames/frame_corner_2px",
      style = {
        color = Color.terminal_corner_hover(255, true),
        offset = { controls_x, row_y, 9 },
        size = { controls_width, row_height },
        scale_to_material = true,
      },
      visibility_function = function (content)
        return content.exclusive_focus and content.gamepad_selected_control == channel_index
      end,
    },
    {
      pass_type = "text",
      style_id = value_id,
      value = "0",
      value_id = value_id,
      style = value_style,
    },
  }
end

local function append_row_focus_pass(passes, value_width, height)
  passes[#passes + 1] = {
    pass_type = "texture",
    value = "content/ui/materials/frames/hover",
    style = {
      hdr = true,
      horizontal_alignment = "right",
      vertical_alignment = "top",
      color = Color.terminal_corner_hover(255, true),
      offset = { 0, 0, 11 },
      size = { value_width, height },
      size_addition = { 0, 0 },
    },
    change_function = function (content, style)
      local hotspot = content.hotspot
      local focus_progress = hotspot.use_is_focused and hotspot.anim_focus_progress or hotspot.anim_select_progress
      local progress = math.max(hotspot.anim_hover_progress, focus_progress)

      style.color[1] = 255 * math.easeOutCubic(progress)

      local size_addition = HIGHLIGHT_SIZE_ADDITION * math.easeInCubic(1 - progress)

      style.size_addition[1] = size_addition * 2
      style.size_addition[2] = size_addition * 2
      style.offset[1] = size_addition
      style.offset[2] = -size_addition
      style.hdr = progress == 1
    end,
    visibility_function = function (content)
      local hotspot = content.hotspot

      if content.exclusive_focus and content.gamepad_selected_control then
        return false
      end

      return (hotspot.is_hover or hotspot.is_selected or hotspot.is_focused) and not content.disabled
    end,
  }
end

local function create_pass_template(width, height, settings_value_width, has_alpha)
  local header_width = width - settings_value_width
  local preview_x = header_width
  local controls_x = preview_x + PREVIEW_SIZE + PREVIEW_GAP
  local controls_width = settings_value_width - PREVIEW_SIZE - PREVIEW_GAP
  local first_channel = has_alpha and 1 or 2
  local channels = {}

  for i = first_channel, #CHANNELS do
    channels[#channels + 1] = CHANNELS[i]
  end

  local passes = ListHeaderPassTemplates.list_header(header_width, height, true)

  append_row_focus_pass(passes, settings_value_width, height)

  passes[#passes + 1] = {
    pass_type = "logic",
    value = create_drag_logic(channels, has_alpha, controls_x, controls_width),
  }

  table.append(passes, create_preview_passes(preview_x))

  for i = 1, #channels do
    table.append(passes, create_channel_passes(channels[i], i, #channels, controls_x, controls_width, height))
  end

  return passes
end

return {
  create = create_pass_template,
  stop_drag = stop_drag,
}
