---@class DMFMod
local dmf = get_mod("DMF")

local _view_settings = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view_settings")
local FilterInput = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/filter/filter_input")

local ScrollbarPassTemplates = require("scripts/ui/pass_templates/scrollbar_pass_templates")
local UIFontSettings = require("scripts/managers/ui/ui_font_settings")
local UIWidget = require("scripts/managers/ui/ui_widget")
local UIWorkspaceSettings = require("scripts/settings/ui/ui_workspace_settings")

local scrollbar_width = _view_settings.scrollbar_width

local grid_size = _view_settings.grid_size
local grid_width = grid_size[1]
local grid_height = grid_size[2]
local grid_blur_edge_size = _view_settings.grid_blur_edge_size
local category_filter_height = _view_settings.category_filter_height
local category_filter_spacing = _view_settings.category_filter_spacing
local category_filter_offset = category_filter_height + category_filter_spacing
local category_content_height = grid_height - category_filter_offset
local category_panel_y = 180

local category_mask_size = {
  grid_width + grid_blur_edge_size[1] * 2,
  category_content_height + grid_blur_edge_size[2] * 2
}
local settings_header_offset = _view_settings.settings_header_height + _view_settings.settings_header_spacing
local settings_header_y = _view_settings.settings_header_y
local settings_grid_y = settings_header_y + settings_header_offset
local content_bottom = category_panel_y + grid_height
local settings_grid_height = content_bottom - settings_grid_y
local settings_mask_size = {
  1080 + grid_blur_edge_size[1] * 2,
  settings_grid_height + grid_blur_edge_size[2] * 2
}

local tooltip_text_style = table.clone(UIFontSettings.body)
tooltip_text_style.text_horizontal_alignment = "left"
tooltip_text_style.text_vertical_alignment = "top"
tooltip_text_style.horizontal_alignment = "left"
tooltip_text_style.vertical_alignment = "top"
tooltip_text_style.color = Color.white(255, true)
tooltip_text_style.offset = {
  0,
  0,
  2
}

local tooltip_metadata_text_style = table.clone(UIFontSettings.body_small)
tooltip_metadata_text_style.text_horizontal_alignment = "left"
tooltip_metadata_text_style.text_vertical_alignment = "top"
tooltip_metadata_text_style.horizontal_alignment = "left"
tooltip_metadata_text_style.vertical_alignment = "top"
tooltip_metadata_text_style.text_color = Color.ui_grey_light(255, true)
tooltip_metadata_text_style.offset = { 0, 0, 2 }

local tooltip_identifier_text_style = table.clone(tooltip_text_style)
tooltip_identifier_text_style.font_size = 20
tooltip_identifier_text_style.text_color = Color.ui_grey_medium(255, true)

local scenegraph_definition = {
  screen = UIWorkspaceSettings.screen,
  tooltip = {
    vertical_alignment = "top",
    parent = "screen",
    horizontal_alignment = "left",
    size = {
      0,
      0
    },
    position = {
      0,
      0,
      200
    }
  },
  category_filter = {
    vertical_alignment = "top",
    parent = "screen",
    horizontal_alignment = "left",
    size = {
      grid_width,
      category_filter_height
    },
    position = {
      140,
      category_panel_y,
      2
    }
  },
  background = {
    vertical_alignment = "top",
    parent = "screen",
    horizontal_alignment = "left",
    size = {
      grid_width,
      category_content_height
    },
    -- Move the categories up and left to compensate for removed icons
    position = {
      140,
      category_panel_y + category_filter_offset,
      1
    }
  },
  background_icon = {
    vertical_alignment = "center",
    parent = "screen",
    horizontal_alignment = "center",
    size = {
      1250,
      1250
    },
    position = {
      0,
      0,
      0
    }
  },
  grid_start = {
    vertical_alignment = "top",
    parent = "background",
    horizontal_alignment = "left",
    size = {
      0,
      0
    },
    position = {
      0,
      0,
      0
    }
  },
  grid_content_pivot = {
    vertical_alignment = "top",
    parent = "grid_start",
    horizontal_alignment = "left",
    size = {
      0,
      0
    },
    position = {
      0,
      0,
      1
    }
  },
  grid_mask = {
    vertical_alignment = "center",
    parent = "background",
    horizontal_alignment = "center",
    size = category_mask_size,
    position = {
      0,
      0,
      0
    }
  },
  grid_interaction = {
    vertical_alignment = "top",
    parent = "background",
    horizontal_alignment = "left",
    size = {
      grid_width + scrollbar_width * 2,
      category_mask_size[2]
    },
    position = {
      0,
      0,
      0
    }
  },
  scrollbar = {
    vertical_alignment = "center",
    parent = "background",
    horizontal_alignment = "right",
    size = {
      scrollbar_width,
      category_content_height
    },
    position = {
      50,
      0,
      1
    }
  },
  button = {
    vertical_alignment = "left",
    parent = "grid_content_pivot",
    horizontal_alignment = "top",
    size = {
      500,
      64
    },
    position = {
      0,
      0,
      0
    }
  },
  title_divider = {
    vertical_alignment = "top",
    parent = "screen",
    horizontal_alignment = "left",
    size = {
      335,
      18
    },
    position = {
      180,
      135,
      1
    }
  },
  title_text = {
    vertical_alignment = "bottom",
    parent = "title_divider",
    horizontal_alignment = "left",
    size = {
      500,
      50
    },
    position = {
      0,
      -35,
      1
    }
  },
  settings_header = {
    vertical_alignment = "top",
    parent = "screen",
    horizontal_alignment = "right",
    size = {
      1000,
      _view_settings.settings_header_height
    },
    position = {
      -180,
      settings_header_y,
      1
    }
  },
  settings_grid_background = {
    vertical_alignment = "top",
    parent = "screen",
    horizontal_alignment = "right",
    size = {
      1000,
      settings_grid_height
    },
    position = {
      -180,
      settings_grid_y,
      1
    }
  },
  settings_grid_start = {
    vertical_alignment = "top",
    parent = "settings_grid_background",
    horizontal_alignment = "left",
    size = {
      0,
      0
    },
    position = {
      0,
      0,
      0
    }
  },
  settings_grid_content_pivot = {
    vertical_alignment = "top",
    parent = "settings_grid_start",
    horizontal_alignment = "left",
    size = {
      0,
      0
    },
    position = {
      0,
      0,
      1
    }
  },
  settings_scrollbar = {
    vertical_alignment = "top",
    parent = "settings_grid_background",
    horizontal_alignment = "right",
    size = {
      scrollbar_width,
      settings_grid_height
    },
    position = {
      50,
      0,
      1
    }
  },
  settings_grid_mask = {
    vertical_alignment = "center",
    parent = "settings_grid_background",
    horizontal_alignment = "center",
    size = settings_mask_size,
    position = {
      0,
      0,
      0
    }
  },
  settings_grid_interaction = {
    vertical_alignment = "top",
    parent = "settings_grid_background",
    horizontal_alignment = "left",
    size = {
      1000 + scrollbar_width * 2,
      settings_grid_height
    },
    position = {
      0,
      0,
      0
    }
  }
}

local widget_definitions = {
  category_filter = UIWidget.create_definition(FilterInput.create_passes(), "category_filter", {
    input_text = "",
    placeholder_text = " \u{e04a}",
  }),
  settings_overlay = UIWidget.create_definition({
    {
      pass_type = "rect",
      style = {
        offset = {
          0,
          0,
          20
        },
        color = {
          160,
          0,
          0,
          0
        }
      }
    }
  }, "screen"),
  background = UIWidget.create_definition({
    {
      pass_type = "rect",
      style = {
        color = Color.black(255, true)
      }
    },
    {
      pass_type = "texture",
      value = "content/ui/materials/backgrounds/terminal_basic",
      style = {
        horizontal_alignment = "center",
        vertical_alignment = "center",
        scale_to_material = true,
        size_addition = {
          40,
          40
        },
        offset = {
          -20,
          -20,
          0
        },
        color = Color.terminal_grid_background_gradient(204, true)
      }
    }
  }, "screen"),
  title_divider = UIWidget.create_definition({
    {
      pass_type = "texture",
      value = "content/ui/materials/dividers/skull_rendered_left_01"
    }
  }, "title_divider"),
  title_text = UIWidget.create_definition({
    {
      value_id = "text",
      style_id = "text",
      pass_type = "text",
      value = dmf:localize("mods_options"),
      style = table.clone(UIFontSettings.header_1)
    }
  }, "title_text"),
  background_icon = UIWidget.create_definition({
    {
      value = "content/ui/vector_textures/symbols/cog_skull_01",
      pass_type = "slug_icon",
      style = {
        offset = {
          0,
          0,
          0
        },
        color = {
          80,
          0,
          0,
          0
        }
      }
    }
  }, "background_icon"),
  tooltip = UIWidget.create_definition({
    {
      pass_type = "rect",
      style = {
        vertical_alignment = "center",
        horizontal_alignment = "center",
        offset = {
          0,
          0,
          0
        },
        color = Color.ui_terminal(255, true)
      }
    },
    {
      pass_type = "rect",
      style = {
        vertical_alignment = "center",
        horizontal_alignment = "center",
        offset = {
          0,
          0,
          1
        },
        color = Color.black(255, true),
        size_addition = {
          -3,
          -3
        }
      }
    },
    {
      value_id = "identifier_text",
      style_id = "identifier_text",
      pass_type = "text",
      value = "",
      style = tooltip_identifier_text_style
    },
    {
      value_id = "metadata_text",
      style_id = "metadata_text",
      pass_type = "text",
      value = "",
      style = tooltip_metadata_text_style
    },
    {
      value_id = "text",
      style_id = "text",
      pass_type = "text",
      value = "",
      style = tooltip_text_style
    }
  }, "tooltip", {
    visible = false
  }),
  scrollbar = UIWidget.create_definition(ScrollbarPassTemplates.default_scrollbar, "scrollbar", {
    scroll_speed = 10,
  }),
  grid_mask = UIWidget.create_definition({
    {
      value = "content/ui/materials/offscreen_masks/ui_overlay_offscreen_vertical_blur",
      pass_type = "texture",
      style = {
        color = {
          255,
          255,
          255,
          255
        }
      }
    }
  }, "grid_mask"),
  grid_interaction = UIWidget.create_definition({
    {
      pass_type = "hotspot",
      content_id = "hotspot"
    }
  }, "grid_interaction"),
  settings_scrollbar = UIWidget.create_definition(ScrollbarPassTemplates.default_scrollbar, "settings_scrollbar", {
    scroll_speed = 10,
  }),
  settings_grid_mask = UIWidget.create_definition({
    {
      value = "content/ui/materials/offscreen_masks/ui_overlay_offscreen_vertical_blur",
      pass_type = "texture",
      style = {
        color = {
          255,
          255,
          255,
          255
        }
      }
    }
  }, "settings_grid_mask"),
  settings_grid_interaction = UIWidget.create_definition({
    {
      pass_type = "hotspot",
      content_id = "hotspot"
    }
  }, "settings_grid_interaction")
}
local legend_inputs = {
  {
    input_action = "back",
    on_pressed_callback = "cb_on_back_pressed",
    display_name = "loc_settings_menu_close_menu",
    alignment = "left_alignment"
  },
  {
    input_action = "next",
    display_name = "loc_settings_menu_reset_to_default",
    on_pressed_callback = "cb_reset_category_to_default",
    visibility_function = function (parent)
      if parent.is_text_input_focused then
        return false
      end
      
      return not not parent._selected_category and parent._categories_by_display_name[parent._selected_category].can_be_reset
    end
  }
}

local DMFOptionsViewDefinitions = {
  legend_inputs = legend_inputs,
  widget_definitions = widget_definitions,
  scenegraph_definition = scenegraph_definition
}

return settings("DMFOptionsViewDefinitions", DMFOptionsViewDefinitions)
