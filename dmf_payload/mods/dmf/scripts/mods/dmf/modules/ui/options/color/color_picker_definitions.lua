local dmf = get_mod("DMF")

local TextInputUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/text_input_utils")

local ButtonPassTemplates = require("scripts/ui/pass_templates/button_pass_templates")
local UIResolution = require("scripts/managers/ui/ui_resolution")
local UIWidget = require("scripts/managers/ui/ui_widget")
local UIWorkspaceSettings = require("scripts/settings/ui/ui_workspace_settings")

local POPUP_HEIGHT = 650
local PICKER_SIZE = 260
local HUE_WIDTH = 24
local ALPHA_WIDTH = 24
local PREVIEW_SIZE = 100
local FIELD_HEIGHT = 40
local BUTTON_WIDTH = 374
local BUTTON_HEIGHT = 50
local ALPHA_SEGMENTS = 16
local HUE_COLORS = {
  { 255, 255, 0, 0 },
  { 255, 255, 255, 0 },
  { 255, 0, 255, 0 },
  { 255, 0, 255, 255 },
  { 255, 0, 0, 255 },
  { 255, 255, 0, 255 },
  { 255, 255, 0, 0 },
}

local INPUT_FIELDS = {
  "r",
  "g",
  "b",
  "h",
  "s",
  "v",
  "hex",
}

local INPUT_LABELS = {
  r = "R",
  g = "G",
  b = "B",
  h = "H",
  s = "S",
  v = "V",
  hex = "HEX",
  a = "Alpha",
}
local GAMEPAD_FOCUS_PADDING = 8
local GAMEPAD_FOCUS_COLOR = Color.terminal_corner_hover_bright(255, true)
local GAMEPAD_ACTIVE_COLOR = Color.terminal_corner_selected(255, true)

local function copy_style_color(target, source)
  for i = 1, 4 do
    target[i] = source[i]
  end
end

local function create_checkerboard_passes(width, height, columns, rows, layer)
  local passes = {
    {
      pass_type = "rect",
      style_id = "checkerboard_background",
      style = {
        color = { 255, 255, 255, 255 },
        offset = { 0, 0, layer },
        size = { width, height },
      },
    },
  }
  local tile_width = width / columns
  local tile_height = height / rows

  for row = 0, rows - 1 do
    for column = 0, columns - 1 do
      if (row + column) % 2 == 0 then
        passes[#passes + 1] = {
          pass_type = "rect",
          style_id = string.format("checkerboard_%d_%d", row, column),
          style = {
            color = { 255, 204, 204, 204 },
            offset = { column * tile_width, row * tile_height, layer + 1 },
            size = { tile_width, tile_height },
          },
        }
      end
    end
  end

  return passes
end

local function create_pointer_logic_pass()
  return {
    pass_type = "logic",
    value = function (pass_, renderer, style_, content, position, size)
      local input_service = renderer.input_service

      if not input_service or input_service:is_null_service() then
        return
      end

      if not content.drag_active then
        if not content.hotspot.on_pressed then
          return
        end

        content.drag_active = true
      end

      if not input_service:get("left_hold") then
        content.drag_active = nil

        return
      end

      local cursor = UIResolution.inverse_scale_vector(input_service:get("cursor"), renderer.inverse_scale)

      local normalized_x = math.clamp((cursor[1] - position[1]) / size[1], 0, 1)
      local normalized_y = math.clamp((cursor[2] - position[2]) / size[2], 0, 1)
      local on_pointer_changed = content.on_pointer_changed

      if on_pointer_changed then
        on_pointer_changed(normalized_x, normalized_y)
      end
    end,
  }
end

local function append_indicator_outline_passes(
  passes, width, height, offset_x, offset_y, layer, x_content_id, y_content_id
)
  local function append_frame(prefix, inset, color, z)
    local frame_width = width - inset * 2
    local frame_height = height - inset * 2
    local frame_x = offset_x + inset
    local frame_y = offset_y + inset
    local parts = {
      { "top", frame_x, frame_y, frame_width, 1 },
      { "bottom", frame_x, frame_y + frame_height - 1, frame_width, 1 },
      { "left", frame_x, frame_y + 1, 1, frame_height - 2 },
      { "right", frame_x + frame_width - 1, frame_y + 1, 1, frame_height - 2 },
    }

    for i = 1, #parts do
      local part = parts[i]
      local part_x = part[2]
      local part_y = part[3]

      passes[#passes + 1] = {
        pass_type = "rect",
        style_id = prefix .. "_" .. part[1],
        style = {
          color = color,
          offset = { part_x, part_y, z },
          size = { part[4], part[5] },
        },
        change_function = function (content, style)
          style.offset[1] = part_x + (x_content_id and content[x_content_id] or 0)
          style.offset[2] = part_y + (y_content_id and content[y_content_id] or 0)
        end,
      }
    end
  end

  append_frame("indicator_outer", 0, Color.black(255, true), layer)
  append_frame("indicator_inner", 1, Color.white(255, true), layer + 1)
end

local function create_label_definition(text, scenegraph_id)
  return UIWidget.create_definition({
    {
      pass_type = "text",
      value = text,
      style = {
        font_type = "proxima_nova_bold",
        font_size = 18,
        text_color = Color.terminal_text_body(255, true),
        text_horizontal_alignment = "left",
        text_vertical_alignment = "center",
      },
    },
  }, scenegraph_id)
end

local function create_gamepad_focus_pass(layer)
  return {
    pass_type = "texture",
    value = "content/ui/materials/frames/frame_corner_2px",
    style = {
      color = table.clone(GAMEPAD_FOCUS_COLOR),
      offset = { -GAMEPAD_FOCUS_PADDING, -GAMEPAD_FOCUS_PADDING, layer },
      size_addition = { GAMEPAD_FOCUS_PADDING * 2, GAMEPAD_FOCUS_PADDING * 2 },
      scale_to_material = true,
    },
    change_function = function (content, style)
      local color = content.gamepad_active and GAMEPAD_ACTIVE_COLOR or GAMEPAD_FOCUS_COLOR

      copy_style_color(style.color, color)
    end,
    visibility_function = function (content)
      return content.gamepad_focused
    end,
  }
end

local function create_definitions(has_alpha)
  local field_names = table.clone(INPUT_FIELDS)
  local sv_x = -110
  local hue_x = 45
  local preview_x = 180
  local detail_x = preview_x
  local hex_label_y = -110
  local hex_input_y = -80

  if has_alpha then
    field_names[#field_names + 1] = "a"
  end

  local scenegraph_definition = {
    screen = UIWorkspaceSettings.screen,
    center_pivot = {
      parent = "screen",
      horizontal_alignment = "center",
      vertical_alignment = "center",
      size = { 0, 0 },
      position = { 0, 0, 3 },
    },
    title = {
      parent = "center_pivot",
      horizontal_alignment = "center",
      vertical_alignment = "top",
      size = { 1000, 40 },
      position = { 0, -285, 3 },
    },
    sv = {
      parent = "center_pivot",
      horizontal_alignment = "center",
      vertical_alignment = "top",
      size = { PICKER_SIZE, PICKER_SIZE },
      position = { sv_x, -220, 3 },
    },
    hue = {
      parent = "center_pivot",
      horizontal_alignment = "center",
      vertical_alignment = "top",
      size = { HUE_WIDTH, PICKER_SIZE },
      position = { hue_x, -220, 3 },
    },
    preview = {
      parent = "center_pivot",
      horizontal_alignment = "center",
      vertical_alignment = "top",
      size = { PREVIEW_SIZE, PREVIEW_SIZE },
      position = { preview_x, -220, 3 },
    },
    back_button = {
      parent = "center_pivot",
      horizontal_alignment = "center",
      vertical_alignment = "top",
      size = { BUTTON_WIDTH, BUTTON_HEIGHT },
      position = { 0, 225, 3 },
    },
    hex_label = {
      parent = "center_pivot",
      horizontal_alignment = "center",
      vertical_alignment = "top",
      size = { 120, 24 },
      position = { detail_x, hex_label_y, 3 },
    },
  }
  local widget_definitions = {
    overlay = UIWidget.create_definition({
      {
        pass_type = "rect",
        style = {
          color = Color.black(150, true),
          offset = { 0, 0, 1 },
        },
      },
    }, "screen"),
    popup_background = UIWidget.create_definition({
      {
        pass_type = "texture_uv",
        style_id = "terminal",
        value = "content/ui/materials/backgrounds/terminal_basic",
        style = {
          horizontal_alignment = "center",
          vertical_alignment = "center",
          color = Color.terminal_grid_background(255, true),
          offset = { 0, 0, 2 },
          size = { nil, 0 },
          size_addition = { 40, POPUP_HEIGHT + 26 },
          scale_to_material = true,
        },
      },
      {
        pass_type = "texture_uv",
        style_id = "texture",
        value = "content/ui/materials/backgrounds/popups/screen_takeover_01",
        style = {
          horizontal_alignment = "center",
          vertical_alignment = "center",
          color = Color.terminal_background(255, true),
          offset = { 0, 0, 3 },
          size = { 1822, 430 },
        },
      },
    }, "screen"),
    edge_top = UIWidget.create_definition({
      {
        pass_type = "texture_uv",
        value = "content/ui/materials/dividers/horizontal_dynamic_upper",
        style = {
          horizontal_alignment = "center",
          vertical_alignment = "center",
          offset = { 0, -POPUP_HEIGHT * 0.5, 4 },
          size = { 1920, 10 },
          size_addition = { 50, 0 },
          scale_to_material = true,
        },
      },
      {
        pass_type = "texture",
        value = "content/ui/materials/dividers/skull_rendered_center_01",
        style = {
          horizontal_alignment = "center",
          vertical_alignment = "center",
          offset = { 0, -POPUP_HEIGHT * 0.5, 5 },
          size = { 140, 18 },
          scale_to_material = true,
        },
      },
    }, "screen"),
    edge_bottom = UIWidget.create_definition({
      {
        pass_type = "texture_uv",
        value = "content/ui/materials/dividers/horizontal_dynamic_lower",
        style = {
          horizontal_alignment = "center",
          vertical_alignment = "center",
          offset = { 0, POPUP_HEIGHT * 0.5, 4 },
          size = { 1920, 10 },
          size_addition = { 50, 0 },
          scale_to_material = true,
        },
      },
      {
        pass_type = "texture",
        value = "content/ui/materials/dividers/skull_rendered_center_02",
        style = {
          horizontal_alignment = "center",
          vertical_alignment = "center",
          offset = { 0, POPUP_HEIGHT * 0.5 + 10, 5 },
          size = { 306, 48 },
          scale_to_material = true,
        },
      },
    }, "screen"),
    title = UIWidget.create_definition({
      {
        pass_type = "text",
        value_id = "text",
        style = {
          font_type = "proxima_nova_bold",
          font_size = 32,
          text_color = Color.terminal_text_header(255, true),
          text_horizontal_alignment = "center",
          text_vertical_alignment = "center",
        },
      },
    }, "title"),
    hex_label = create_label_definition("HEX", "hex_label"),
    back_button = UIWidget.create_definition(ButtonPassTemplates.terminal_button_small, "back_button"),
  }

  local sv_passes = {
    {
      pass_type = "rect",
      style_id = "hue",
      style = {
        color = Color.red(255, true),
      },
      change_function = function (content, style)
        copy_style_color(style.color, content.hue_color)
      end,
    },
    {
      pass_type = "texture_uv",
      value = "content/ui/materials/gradients/gradient_horizontal",
      style = {
        color = Color.white(255, true),
        uvs = { { 1, 0 }, { 0, 1 } },
        offset = { 0, 0, 1 },
      },
    },
    {
      pass_type = "texture_uv",
      value = "content/ui/materials/gradients/gradient_vertical",
      style = {
        color = Color.black(255, true),
        uvs = { { 0, 0 }, { 1, 1 } },
        offset = { 0, 0, 2 },
      },
    },
    {
      content_id = "hotspot",
      pass_type = "hotspot",
      style = {
        offset = { 0, 0, 4 },
      },
    },
    create_pointer_logic_pass(),
  }

  append_indicator_outline_passes(sv_passes, 22, 22, -11, -11, 5, "sv_x", "sv_y")
  sv_passes[#sv_passes + 1] = create_gamepad_focus_pass(7)

  widget_definitions.sv = UIWidget.create_definition(sv_passes, "sv")

  local hue_passes = {}
  local hue_height = PICKER_SIZE / 6

  for i = 1, 6 do
    local start_color = HUE_COLORS[i]
    local end_color = HUE_COLORS[i + 1]
    local y = (i - 1) * hue_height

    hue_passes[#hue_passes + 1] = {
      pass_type = "rect",
      style_id = "segment_start_" .. i,
      style = {
        color = start_color,
        offset = { 0, y, 0 },
        size = { HUE_WIDTH, hue_height },
      },
    }
    hue_passes[#hue_passes + 1] = {
      pass_type = "texture_uv",
      value = "content/ui/materials/gradients/gradient_vertical",
      style = {
        color = end_color,
        offset = { 0, y, 1 },
        size = { HUE_WIDTH, hue_height },
        uvs = { { 0, 0 }, { 1, 1 } },
      },
    }
  end

  hue_passes[#hue_passes + 1] = {
    content_id = "hotspot",
    pass_type = "hotspot",
    style = {
      offset = { 0, 0, 3 },
    },
  }
  hue_passes[#hue_passes + 1] = create_pointer_logic_pass()
  append_indicator_outline_passes(hue_passes, HUE_WIDTH + 12, 9, -6, -4, 4, nil, "hue_y")
  hue_passes[#hue_passes + 1] = create_gamepad_focus_pass(6)

  widget_definitions.hue = UIWidget.create_definition(hue_passes, "hue")

  local preview_passes = create_checkerboard_passes(PREVIEW_SIZE, PREVIEW_SIZE, 4, 4, 0)

  preview_passes[#preview_passes + 1] = {
    pass_type = "rect",
    style_id = "color",
    style = {
      color = Color.white(255, true),
      offset = { 0, 0, 3 },
    },
    change_function = function (content, style)
      copy_style_color(style.color, content.draft_color)
    end,
  }
  preview_passes[#preview_passes + 1] = {
    pass_type = "texture",
    value = "content/ui/materials/frames/frame_tile_2px",
    style = {
      color = Color.terminal_frame(255, true),
      offset = { 0, 0, 4 },
      scale_to_material = true,
    },
  }

  widget_definitions.preview = UIWidget.create_definition(preview_passes, "preview")

  local field_positions = {
    r = { -156, 70, 110 },
    g = { 14, 70, 110 },
    b = { 184, 70, 110 },
    h = { -156, 125, 110 },
    s = { 14, 125, 110 },
    v = { 184, 125, 110 },
    hex = { detail_x, hex_input_y, 120 },
    a = { detail_x, -5, 120 },
  }
  local label_positions = {
    r = { -226, 70, 25, FIELD_HEIGHT },
    g = { -56, 70, 25, FIELD_HEIGHT },
    b = { 114, 70, 25, FIELD_HEIGHT },
    h = { -226, 125, 25, FIELD_HEIGHT },
    s = { -56, 125, 25, FIELD_HEIGHT },
    v = { 114, 125, 25, FIELD_HEIGHT },
    a = { detail_x, -35, 120, 24 },
  }

  for i = 1, #field_names do
    local field_name = field_names[i]
    local field_position = field_positions[field_name]
    local label_position = label_positions[field_name]

    scenegraph_definition["input_" .. field_name] = {
      parent = "center_pivot",
      horizontal_alignment = "center",
      vertical_alignment = "top",
      size = { field_position[3], FIELD_HEIGHT },
      position = { field_position[1], field_position[2], 3 },
    }
    local input_passes = TextInputUtils.clone_simple_input_field()

    for j = 1, #input_passes do
      if input_passes[j].style_id == "limit_text" then
        input_passes[j].visibility_function = function ()
          return false
        end

        break
      end
    end

    widget_definitions["input_" .. field_name] = UIWidget.create_definition(input_passes, "input_" .. field_name)

    if label_position then
      scenegraph_definition["label_" .. field_name] = {
        parent = "center_pivot",
        horizontal_alignment = "center",
        vertical_alignment = "top",
        size = { label_position[3], label_position[4] },
        position = { label_position[1], label_position[2], 3 },
      }
      widget_definitions["label_" .. field_name] = create_label_definition(
        INPUT_LABELS[field_name],
        "label_" .. field_name
      )
    end
  end

  if has_alpha then
    scenegraph_definition.alpha = {
      parent = "center_pivot",
      horizontal_alignment = "center",
      vertical_alignment = "top",
      size = { ALPHA_WIDTH, PICKER_SIZE },
      position = { 80, -220, 3 },
    }

    local alpha_passes = create_checkerboard_passes(ALPHA_WIDTH, PICKER_SIZE, 2, ALPHA_SEGMENTS, 0)
    local segment_height = PICKER_SIZE / ALPHA_SEGMENTS

    for i = 1, ALPHA_SEGMENTS do
      local segment_alpha = math.round(255 * (1 - (i - 0.5) / ALPHA_SEGMENTS))

      alpha_passes[#alpha_passes + 1] = {
        pass_type = "rect",
        style_id = "alpha_segment_" .. i,
        style = {
          color = { segment_alpha, 255, 255, 255 },
          offset = { 0, (i - 1) * segment_height, 3 },
          size = { ALPHA_WIDTH, segment_height },
        },
        change_function = function (content, style)
          style.color[2] = content.draft_color[2]
          style.color[3] = content.draft_color[3]
          style.color[4] = content.draft_color[4]
        end,
      }
    end

    alpha_passes[#alpha_passes + 1] = {
      content_id = "hotspot",
      pass_type = "hotspot",
      style = {
        offset = { 0, 0, 4 },
      },
    }
    alpha_passes[#alpha_passes + 1] = create_pointer_logic_pass()
    append_indicator_outline_passes(alpha_passes, ALPHA_WIDTH + 12, 9, -6, -4, 5, nil, "alpha_y")
    alpha_passes[#alpha_passes + 1] = create_gamepad_focus_pass(7)

    widget_definitions.alpha = UIWidget.create_definition(alpha_passes, "alpha")
  end

  local gamepad_navigation_items = {
    { id = "sv", widget_name = "sv", kind = "picker" },
    { id = "hue", widget_name = "hue", kind = "picker" },
    { id = "r", widget_name = "input_r", kind = "field" },
    { id = "g", widget_name = "input_g", kind = "field" },
    { id = "b", widget_name = "input_b", kind = "field" },
    { id = "h", widget_name = "input_h", kind = "field" },
    { id = "s", widget_name = "input_s", kind = "field" },
    { id = "v", widget_name = "input_v", kind = "field" },
    { id = "hex", widget_name = "input_hex", kind = "field" },
    { id = "back", widget_name = "back_button", kind = "button" },
  }

  if has_alpha then
    gamepad_navigation_items[#gamepad_navigation_items + 1] = { id = "alpha", widget_name = "alpha", kind = "picker" }
    gamepad_navigation_items[#gamepad_navigation_items + 1] = { id = "a", widget_name = "input_a", kind = "field" }
  end

  local navigation = {
    sv = { right = "hue", down = "r" },
    hue = { left = "sv", right = has_alpha and "alpha" or "hex", down = "g" },
    r = { right = "g", up = "sv", down = "h" },
    g = { left = "r", right = "b", up = "hue", down = "s" },
    b = { left = "g", up = has_alpha and "a" or "hex", down = "v" },
    h = { right = "s", up = "r", down = "back" },
    s = { left = "h", right = "v", up = "g", down = "back" },
    v = { left = "s", up = "b", down = "back" },
    hex = {
      left = has_alpha and "alpha" or "hue",
      down = has_alpha and "a" or "b",
    },
    back = { up = "s" },
  }

  if has_alpha then
    navigation.alpha = { left = "hue", right = "hex", down = "g" }
    navigation.a = { left = "alpha", up = "hex", down = "b" }
  end

  for i = 1, #gamepad_navigation_items do
    local item = gamepad_navigation_items[i]

    item.navigation = navigation[item.id]
  end

  return {
    scenegraph_definition = scenegraph_definition,
    widget_definitions = widget_definitions,
  }, field_names, gamepad_navigation_items
end

return {
  create = create_definitions,
  picker_size = PICKER_SIZE,
}
