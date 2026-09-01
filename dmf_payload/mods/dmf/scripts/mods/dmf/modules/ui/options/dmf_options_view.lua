---@class DMFMod
local dmf = get_mod("DMF")

local _widgets_by_name

-- ####################################################################################################################
-- ##### Local functions ##############################################################################################
-- ####################################################################################################################

local DEFAULT_SCROLL_STEP = 300
local PAGE_OVERLAP_RATIO = 0.1
local MOD_SCROLL_OFFSETS_SETTING = "options_menu_mod_scroll_offsets"
local TOGGLE_MODS_SCROLL_OFFSET_SETTING = "options_menu_toggle_mods_scroll_offset"
local SHOW_MOD_OPTION_IDS_SETTING = "show_mod_option_ids"
local FAVORITE_MODS_SETTING = "options_menu_favorite_mods"

local function values_equal(left, right)
  if type(left) == "table" and type(right) == "table" then
    return table.equals(left, right)
  end

  return left == right
end

local function setting_requires_restart(entry, option_value)
  if entry.require_restart then
    return true
  end

  if option_value ~= nil and entry.options then
    for i = 1, #entry.options do
      local option = entry.options[i]

      if option.value == option_value then
        return option.require_restart or false
      end
    end
  end

  return false
end

local function update_scroll_amount(scrollbar_widget)
  local content = scrollbar_widget.content
  local scroll_length = content.scroll_length

  if not scroll_length or scroll_length <= 0 then
    return
  end

  local speed_multiplier = math.clamp((dmf:get("dmf_options_scrolling_speed") or 100) / 100, 0.5, 5)
  local desired_step = DEFAULT_SCROLL_STEP * speed_multiplier
  local max_step = content.area_length * (1 - PAGE_OVERLAP_RATIO)
  local pixel_step = math.min(desired_step, max_step, scroll_length)

  content.scroll_amount = pixel_step / scroll_length
end

local function load_scrolling_speed_setting()
  if _widgets_by_name then
    update_scroll_amount(_widgets_by_name.scrollbar)
    update_scroll_amount(_widgets_by_name.settings_scrollbar)
  end
end

-- ####################################################################################################################
-- ##### DMF internal functions and variables #########################################################################
-- ####################################################################################################################

dmf.load_dmf_options_view_settings = function()
  load_scrolling_speed_setting()
end

-- ####################################################################################################################
-- ##### DMF Options View Class #######################################################################################
-- ####################################################################################################################

local _content_blueprints = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view_content_blueprints")
local _view_settings = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view_settings")
local ViewElementColorPicker = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/color/color_picker")
local FilterInput = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/filter/filter_input")
local OptionsFilter = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/filter/options_filter")
local OptionsDisplayUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/options_display_utils")
local ViewElementOptionsHeader = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/header/options_header")
local ViewElementOptionsTabIndicator = dmf:io_dofile(
  "dmf/scripts/mods/dmf/modules/ui/options/tab_indicator/options_tab_indicator"
)

local InputUtils = require("scripts/managers/input/input_utils")
local ScriptWorld = require("scripts/foundation/utilities/script_world")
local UIFonts = require("scripts/managers/ui/ui_fonts")
local UIRenderer = require("scripts/managers/ui/ui_renderer")
local UIWidget = require("scripts/managers/ui/ui_widget")
local UIWidgetGrid = require("scripts/ui/widget_logic/ui_widget_grid")
local ViewElementInputLegend = require("scripts/ui/view_elements/view_element_input_legend/view_element_input_legend")
local ViewElementKeybindPopup = require("scripts/ui/view_elements/view_element_keybind_popup/view_element_keybind_popup")

local CATEGORIES_GRID = 1
local SETTINGS_GRID = 2
local GRID_SCROLL_EPSILON = 0.001
local TOOLTIP_HORIZONTAL_PADDING = 20
local TOOLTIP_VERTICAL_PADDING = 20
local TOOLTIP_SECTION_SPACING = 8
local TOOLTIP_TEXT_HEIGHT_BOUND = 100000

local _last_selected_category_entry
local _last_selected_category_widget

local function grid_item_is_fully_visible(grid, index)
  local target_progress = grid:get_scrollbar_percentage_by_index(index)

  return target_progress == nil
    or math.abs(target_progress - grid:scrollbar_progress()) <= GRID_SCROLL_EPSILON
end

local function focusable_widget_at_scroll_position(widgets, grid)
  if not widgets or not grid then
    return nil
  end

  local scrollbar_progress = grid:scrollbar_progress()
  local last_focusable_widget

  for i = 1, #widgets do
    local widget = widgets[i]
    local content = widget.content
    local hotspot = content.hotspot or content.button_hotspot

    if hotspot then
      last_focusable_widget = widget

      local scroll_position = grid:get_scrollbar_percentage_by_index(i) or 0

      if scrollbar_progress <= scroll_position + GRID_SCROLL_EPSILON then
        return widget
      end
    end
  end

  return last_focusable_widget
end

local function clear_tooltip(view)
  view._tooltip_data = {}
  view._widgets_by_name.tooltip.content.visible = false
end

local function sort_pinned_categories(categories)
  local toggle_categories = {}
  local pinned_categories = {}
  local regular_categories = {}

  table.sort(categories, function (left, right)
    local left_entry = left.entry or left
    local right_entry = right.entry or right

    return left_entry.original_index < right_entry.original_index
  end)

  for i = 1, #categories do
    local category = categories[i]
    local entry = category.entry or category
    local target = entry.is_toggle_mods_category and toggle_categories
      or entry.is_favorited and pinned_categories
      or regular_categories

    target[#target + 1] = category
  end

  table.clear(categories)
  table.append(categories, toggle_categories)
  table.append(categories, pinned_categories)
  table.append(categories, regular_categories)
end

local function update_category_pin_display(category_data)
  local entry = category_data.entry

  category_data.widget.content.text = entry.is_favorited
    and OptionsDisplayUtils.pinned_category_name(entry.display_name)
    or entry.display_name
end

local DMFOptionsView = class("DMFOptionsView", "BaseView")

DMFOptionsView.init = function (self, settings)
  local definitions = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view_definitions")

  DMFOptionsView.super.init(self, definitions, settings)

  self._pass_draw = false

  self:_setup_offscreen_gui()
end

DMFOptionsView.on_enter = function (self)
  _widgets_by_name = self._widgets_by_name

  if not self._options_templates then
    self._options_templates = {
      settings = {},
      categories = {}
    }
    dmf:create_mod_options_settings(self._options_templates)
  end
  DMFOptionsView.super.on_enter(self)

  self._default_category = nil
  self._using_cursor_navigation = Managers.ui:using_cursor_navigation()
  dmf:update_mod_options_visibility(self._options_templates)
  self._validation_mapping = self:_map_validations(self._options_templates)

  self:_setup_category_filter()
  self:_setup_options_header()
  self:_setup_settings_config(self._options_templates)
  self:_setup_category_config(self._options_templates)
  self:_setup_input_legend()
  self:_enable_settings_overlay(false)
  self:_update_grid_navigation_selection()
end

DMFOptionsView._map_validations = function (self, config)
  local config_categories = config.categories
  local categories = {}

  for i = 1, #config_categories do
    local category_config = config_categories[i]
    local validation_result = category_config.validation_function and category_config.validation_function()

    if validation_result == nil then
      validation_result = true
    end

    categories[category_config.display_name] = {
      validation_function = category_config.validation_function,
      validation_result = validation_result,
      settings = {}
    }
  end

  local config_settings = config.settings

  for _, setting in ipairs(config_settings) do
    local validation_result = setting.validation_function and setting.validation_function()

    if validation_result == nil then
      validation_result = true
    end

    categories[setting.category].settings[setting.display_name] = {
      validation_function = setting.validation_function,
      validation_result = validation_result
    }
  end

  return categories
end

DMFOptionsView.on_exit = function (self)
  self:_save_selected_category_scroll_offset()
  _widgets_by_name = nil

  if self._color_picker then
    self:_remove_element("color_picker")
    self._color_picker = nil
  end

  Managers.event:trigger("event_on_input_settings_changed")

  if self._input_legend_element then
    self._input_legend_element = nil

    self:_remove_element("input_legend")
  end

  if self._options_header then
    self._options_header = nil

    self:_remove_element("options_header")
  end

  if self._popup_id then
    Managers.event:trigger("event_remove_ui_popup", self._popup_id)
  end

  if self._ui_offscreen_renderer then
    self._ui_offscreen_renderer = nil

    Managers.ui:destroy_renderer(self.__class_name .. "_ui_offscreen_renderer")

    local offscreen_world = self._offscreen_world
    local offscreen_viewport_name = self._offscreen_viewport_name

    ScriptWorld.destroy_viewport(offscreen_world, offscreen_viewport_name)
    Managers.ui:destroy_world(offscreen_world)

    self._offscreen_viewport = nil
    self._offscreen_viewport_name = nil
    self._offscreen_world = nil
  end

  DMFOptionsView.super.on_exit(self)
end

DMFOptionsView.cb_on_back_pressed = function (self)
  local selected_navigation_column = self._selected_navigation_column_index
  local selected_settings_widget = self._selected_settings_widget
  local category_focus_widget = self._category_filter_focused and self:_category_focus_widget()

  if self:_is_category_filter_writing() then
    FilterInput.finish_editing(self._category_filter_content)
  elseif self._options_header and self._options_header:is_filter_writing() then
    self._options_header:finish_filter_editing()
  elseif selected_settings_widget then
    self._close_selected_setting = true
  elseif category_focus_widget then
    self:_set_selected_navigation_widget(category_focus_widget)
  elseif self._header_navigation_control then
    self:_focus_category_from_header()
  elseif selected_navigation_column == SETTINGS_GRID then
    self:_change_navigation_column(selected_navigation_column - 1)
  elseif self._require_restart then
    self:_restart_popup_info()
  else
    local view_name = "dmf_options_view"
    Managers.ui:close_view(view_name)
  end
end

DMFOptionsView.cb_reset_category_to_default = function (self)
  local selected_category = self._selected_category
  local reset_functions_by_category = self._reset_functions_by_category
  local reset_function = reset_functions_by_category[selected_category]
  local context = {
    title_text = "loc_popup_header_settings_reset_default",
    description_text = "loc_popup_description_settings_reset_default",
    type = "warning",
    options = {
      {
        text = "loc_popup_button_settings_reset_default",
        close_on_pressed = true,
        callback = callback(function ()
          if reset_function then
            reset_function()
          else
            local settings_category_default_values = self._settings_category_default_values
            local settings_default_values = selected_category and settings_category_default_values[selected_category]

            if settings_default_values then
              for setting, default_value in pairs(settings_default_values) do
                local on_activated = setting.on_activated

                if on_activated then
                  local current_value = setting.get_function and setting:get_function()

                  on_activated(default_value, setting)

                  local updated_value = setting.get_function and setting:get_function()

                  if not values_equal(current_value, updated_value) then
                    self:cb_on_settings_changed(nil, setting, updated_value)
                  end
                end
              end

              if self._dynamic_options_changed_entry and self._applied_options_filter == nil then
                self._applied_options_filter = self._options_header:filter_text()
              end
            end
          end

          local category_entry = self._selected_category_entry
          local mod_name = category_entry and category_entry.mod_name

          if mod_name then
            dmf.mod_settings_reset_event(get_mod(mod_name))
          end

          if mod_name and dmf:update_mod_options_visibility(self._options_templates, mod_name) then
            self:_refresh_dynamic_options()
          end

          self._popup_id = nil
        end)
      },
      {
        text = "loc_popup_button_cancel_settings_reset_default",
        template_type = "terminal_button_small",
        close_on_pressed = true,
        hotkey = "back",
        callback = function ()
          self._popup_id = nil
        end
      }
    }
  }

  Managers.event:trigger("event_show_ui_popup", context, function (id)
    self._popup_id = id
  end)
end

DMFOptionsView._restart_popup_info = function (self)
  local context = {
    title_text = "loc_popup_settings_require_restart_header",
    description_text = "loc_popup_settings_require_restart_description",
    options = {
      {
        text = "loc_confirm",
        close_on_pressed = true,
        callback = callback(function ()
          self._popup_id = nil
          local view_name = "dmf_options_view"
          self._require_restart = false

          Managers.ui:close_view(view_name)
        end)
      }
    }
  }

  Managers.event:trigger("event_show_ui_popup", context, function (id)
    self._popup_id = id
  end)
end

DMFOptionsView._setup_input_legend = function (self)
  self._input_legend_element = self:_add_element(ViewElementInputLegend, "input_legend", 10)
  local legend_inputs = self._definitions.legend_inputs

  for i = 1, #legend_inputs do
    local legend_input = legend_inputs[i]
    local on_pressed_callback = legend_input.on_pressed_callback and callback(self, legend_input.on_pressed_callback)

    self._input_legend_element:add_entry(legend_input.display_name, legend_input.input_action, legend_input.visibility_function, on_pressed_callback, legend_input.alignment)
  end
end

DMFOptionsView._setup_options_header = function (self)
  local header_scenegraph = self._ui_scenegraph.settings_header
  local settings_grid_scenegraph = self._ui_scenegraph.settings_grid_background

  self._settings_grid_layout = {
    bottom = settings_grid_scenegraph.world_position[2] + settings_grid_scenegraph.size[2],
    header_y = header_scenegraph.world_position[2],
    interaction_height_delta = self._ui_scenegraph.settings_grid_interaction.size[2] - settings_grid_scenegraph.size[2],
    mask_height_delta = self._ui_scenegraph.settings_grid_mask.size[2] - settings_grid_scenegraph.size[2],
    scrollbar_height_delta = self._ui_scenegraph.settings_scrollbar.size[2] - settings_grid_scenegraph.size[2],
    tab_height = _view_settings.settings_tab_height,
    tab_spacing = _view_settings.settings_tab_spacing,
  }

  self._options_header = self:_add_element(ViewElementOptionsHeader, "options_header", 20, {
    panel_x = header_scenegraph.world_position[1],
    panel_y = header_scenegraph.world_position[2],
    get_pin_value = callback(self, "_get_header_pin_value"),
    get_toggle_value = callback(self, "_get_header_toggle_value"),
    on_pin_changed = callback(self, "_on_header_pin_changed"),
    on_toggle_changed = callback(self, "_on_header_toggle_changed"),
  })
  self._applied_options_filter = ""
end

DMFOptionsView._setup_category_filter = function (self)
  local content = self._widgets_by_name.category_filter.content

  FilterInput.reset(content)

  self._category_filter_content = content
  self._applied_category_filter = ""
end

DMFOptionsView._set_options_header_layout = function (self, header_height, header_spacing, show_tab)
  local layout = self._settings_grid_layout
  local tab_height = show_tab and layout.tab_height + layout.tab_spacing or 0
  local grid_y = layout.header_y + header_height + tab_height + header_spacing
  local grid_height = layout.bottom - grid_y

  self:_set_scenegraph_position("settings_grid_background", nil, grid_y)
  self:_set_scenegraph_size("settings_grid_background", nil, grid_height)
  self:_set_scenegraph_size("settings_grid_interaction", nil, grid_height + layout.interaction_height_delta)
  self:_set_scenegraph_size("settings_grid_mask", nil, grid_height + layout.mask_height_delta)
  self:_set_scenegraph_size("settings_scrollbar", nil, grid_height + layout.scrollbar_height_delta)
  self:_force_update_scenegraph()
end

DMFOptionsView._get_header_toggle_value = function (self, category_entry)
  return get_mod(category_entry.mod_name):is_enabled()
end

DMFOptionsView._on_header_toggle_changed = function (self, category_entry, value)
  dmf.mod_state_changed(category_entry.mod_name, value)
end

DMFOptionsView._get_header_pin_value = function (self, category_entry)
  return category_entry.is_favorited and true or false
end

DMFOptionsView._on_header_pin_changed = function (self, category_entry, value)
  local mod_name = category_entry.mod_name
  local favorited_mods = dmf:get(FAVORITE_MODS_SETTING)
  local updated_favorited_mods = {}
  local category_scroll_progress = self._category_content_grid:scrollbar_progress()

  for i = 1, #favorited_mods do
    if favorited_mods[i] ~= mod_name then
      updated_favorited_mods[#updated_favorited_mods + 1] = favorited_mods[i]
    end
  end

  if value then
    updated_favorited_mods[#updated_favorited_mods + 1] = mod_name
  end

  dmf:set(FAVORITE_MODS_SETTING, updated_favorited_mods)

  category_entry.is_favorited = value

  local categories = self._options_templates.categories

  for i = 1, #categories do
    local category = categories[i]

    if category.mod_name == mod_name then
      category.is_favorited = value

      break
    end
  end

  sort_pinned_categories(self._category_data)

  local selected_category_entry = self._selected_category_entry
  local selected_category_widget

  for i = 1, #self._category_data do
    local data = self._category_data[i]
    local is_selected = data.entry == selected_category_entry
    local hotspot = data.widget.content.hotspot

    update_category_pin_display(data)
    hotspot.is_selected = is_selected
    hotspot.anim_select_progress = is_selected and 1 or 0

    if is_selected then
      selected_category_widget = data.widget
    end
  end

  self._selected_category_widget = selected_category_widget

  OptionsFilter.prepare(self._category_data)
  self:_present_category_filter(
    self._category_filter_content.input_text or "",
    selected_category_widget,
    category_scroll_progress
  )
end

DMFOptionsView._setup_content_grid_scrollbar = function (
  self, grid, widget_id, grid_scenegraph_id, grid_pivot_scenegraph_id, category_position_widget,
  initial_scroll_progress
)
  local widgets_by_name = self._widgets_by_name
  local scrollbar_widget = widgets_by_name[widget_id]

  grid:assign_scrollbar(scrollbar_widget, grid_pivot_scenegraph_id, grid_scenegraph_id, true)
  update_scroll_amount(scrollbar_widget)

  if initial_scroll_progress ~= nil and widget_id == "scrollbar" then
    grid:set_scrollbar_progress(initial_scroll_progress)
    grid:_update_scroll_progress(true)
  end

  -- Scroll the category grid to the requested category widget
  if category_position_widget and widget_id == "scrollbar" then
    local index = grid:index_by_widget(category_position_widget)
    local scroll_progress = index
      and grid:get_scrollbar_percentage_by_index(index)
      or initial_scroll_progress
      or grid:scrollbar_progress()

    grid:set_scrollbar_progress(scroll_progress or 0)
    grid:_update_scroll_progress(true)
  else
    grid:set_scrollbar_progress(0)
  end
end

DMFOptionsView._setup_offscreen_gui = function (self)
  local ui_manager = Managers.ui
  local class_name = self.__class_name
  local timer_name = "ui"
  local world_layer = 10
  local world_name = class_name .. "_ui_offscreen_world"
  local view_name = self.view_name
  self._offscreen_world = ui_manager:create_world(world_name, world_layer, timer_name, view_name)
  local shading_environment = _view_settings.shading_environment
  local viewport_name = class_name .. "_ui_offscreen_world_viewport"
  local viewport_type = "overlay_offscreen"
  local viewport_layer = 1
  self._offscreen_viewport = ui_manager:create_viewport(self._offscreen_world, viewport_name, viewport_type, viewport_layer, shading_environment)
  self._offscreen_viewport_name = viewport_name
  self._ui_offscreen_renderer = ui_manager:create_renderer(class_name .. "_ui_offscreen_renderer", self._offscreen_world)
end

DMFOptionsView._setup_content_widgets = function (self, content, scenegraph_id, callback_name)
  local definitions = self._definitions
  local widget_definitions = {}
  local widgets = {}
  local alignment_list = {}
  local amount = #content

  for i = 1, amount do
    local entry = content[i]
    local verified = true

    if verified then
      local widget_type = entry.widget_type
      local widget = nil
      local template = _content_blueprints[widget_type]
      local size = template.size
      local pass_template = template.pass_template

      if pass_template and not widget_definitions[widget_type] then
        local scenegraph_definition = definitions.scenegraph_definition
        widget_definitions[widget_type] = UIWidget.create_definition(pass_template, scenegraph_id, nil, size)
      end

      local widget_definition = widget_definitions[widget_type]

      if widget_definition then
        local name = scenegraph_id .. "_widget_" .. i
        widget = self:_create_widget(name, widget_definition)
        local init = template.init

        if init then
          init(self, widget, entry, callback_name)
        end

        local focus_group = entry.focus_group

        if focus_group then
          widget.content.focus_group = focus_group
        end

        widgets[#widgets + 1] = widget
      end

      alignment_list[#alignment_list + 1] = widget or {
        size = size
      }

      if entry.display_name == self._default_category then
        _last_selected_category_entry = entry
        _last_selected_category_widget = widget
      end
    end
  end

  return widgets, alignment_list
end

DMFOptionsView._draw_widgets = function (self, dt, t, input_service, ui_renderer)
  local widgets_by_name = self._widgets_by_name
  local scrollbar_widget = widgets_by_name.scrollbar
  scrollbar_widget.content.visible = self._category_content_grid:can_scroll()

  if self._selected_settings_widget then
    UIWidget.draw(self._selected_settings_widget, ui_renderer)
  end

  if self._selected_settings_widget or self._color_picker or self._color_picker_block_input_this_frame then
    input_service = input_service:null_service()
    ui_renderer.input_service = input_service
  end

  DMFOptionsView.super._draw_widgets(self, dt, t, input_service, ui_renderer)
end

DMFOptionsView._draw_elements = function (self, dt, t, ui_renderer, render_settings, input_service)
  if self._color_picker or self._color_picker_block_input_this_frame then
    local elements_array = self._elements_array or {}
    local null_input_service = input_service:null_service()

    for i = 1, #elements_array do
      local element = elements_array[i]

      if element then
        local element_input_service = element == self._color_picker and input_service or null_input_service
        element:draw(dt, t, ui_renderer, render_settings, element_input_service)
      end
    end

    return
  end

  if self:_handling_keybinding() or self._selected_settings_widget then
    input_service = input_service:null_service()
    ui_renderer.input_service = input_service
  end

  DMFOptionsView.super._draw_elements(self, dt, t, ui_renderer, render_settings, input_service)
end

DMFOptionsView._update_elements = function (self, dt, t, input_service)
  if self._color_picker or self._color_picker_block_input_this_frame then
    local elements_array = self._elements_array or {}
    local null_input_service = input_service:null_service()

    for i = 1, #elements_array do
      local element = elements_array[i]

      if element then
        local element_input_service = element == self._color_picker and input_service or null_input_service
        element:update(dt, t, element_input_service)
      end
    end

    return
  end

  DMFOptionsView.super._update_elements(self, dt, t, input_service)
end

DMFOptionsView.draw = function (self, dt, t, input_service, layer)
  if self:_handling_keybinding() then
    input_service = input_service:null_service()
  end

  local background_input_service = input_service
  if self._color_picker or self._color_picker_block_input_this_frame then
    background_input_service = input_service:null_service()
  end

  local widgets_by_name = self._widgets_by_name
  local grid_interaction_widget = widgets_by_name.grid_interaction

  self:_draw_grid(
    self._category_content_grid, self._category_content_widgets, grid_interaction_widget, dt, t,
    background_input_service
  )

  if self._settings_content_grid then
    local grid_interaction_widget = widgets_by_name.settings_grid_interaction

    self:_draw_grid(
      self._settings_content_grid, self._settings_content_widgets, grid_interaction_widget, dt, t,
      background_input_service
    )
  end

  DMFOptionsView.super.draw(self, dt, t, input_service, layer)
end

DMFOptionsView._draw_grid = function (self, grid, widgets, interaction_widget, dt, t, input_service)
  local is_grid_hovered = not self._using_cursor_navigation or interaction_widget.content.hotspot.is_hover or false
  local null_input_service = input_service:null_service()
  local render_settings = self._render_settings
  local ui_renderer = self._ui_offscreen_renderer
  local ui_scenegraph = self._ui_scenegraph
  local color_picker_blocks_background = self._color_picker or self._color_picker_block_input_this_frame
  local show_setting_ids = dmf:get(SHOW_MOD_OPTION_IDS_SETTING)

  UIRenderer.begin_pass(ui_renderer, ui_scenegraph, input_service, dt, render_settings)

  for j = 1, #widgets do
    local widget = widgets[j]
    local draw = widget ~= self._selected_settings_widget

    if draw then
      if self._selected_settings_widget then
        ui_renderer.input_service = null_input_service
      end

      if grid:is_widget_visible(widget) then
        local hotspot = widget.content.hotspot

        if hotspot then
          hotspot.force_disabled = not is_grid_hovered
          local is_active = hotspot.is_focused or hotspot.is_hover
          local entry = widget.content.entry
          local identifier = entry and (entry.tooltip_identifier or show_setting_ids and entry.setting_id)
          local has_tooltip = entry and (
            entry.tooltip_text
            or identifier
            or entry.tooltip_metadata
            or entry.disabled_by and not table.is_empty(entry.disabled_by)
          )

          if not color_picker_blocks_background and is_active and has_tooltip then
            self:_set_tooltip_data(widget, identifier)
          end
        end

        UIWidget.draw(widget, ui_renderer)
      end
    end
  end

  UIRenderer.end_pass(ui_renderer)
end

DMFOptionsView._setup_grid = function (self, widgets, alignment_list, grid_scenegraph_id, spacing, use_is_focused)
  local ui_scenegraph = self._ui_scenegraph
  local direction = "down"
  local grid = UIWidgetGrid:new(widgets, alignment_list, ui_scenegraph, grid_scenegraph_id, direction, spacing, nil, use_is_focused)
  local render_scale = self._render_scale

  grid:set_render_scale(render_scale)

  return grid
end

DMFOptionsView.set_render_scale = function (self, scale)
  DMFOptionsView.super.set_render_scale(self, scale)
  self._category_content_grid:set_render_scale(self._render_scale)

  if self._settings_content_grid then
    self._settings_content_grid:set_render_scale(self._render_scale)
  end

  if self._options_header then
    self._options_header:invalidate_text_layout()
  end
end

DMFOptionsView.update = function (self, dt, t, input_service, view_data)
  self._color_picker_block_input_this_frame = self._color_picker ~= nil or self._color_picker_closed_this_frame
  self._color_picker_closed_this_frame = nil

  local drawing_view = view_data and view_data.drawing_view
  local using_cursor_navigation = Managers.ui:using_cursor_navigation()

  if self._using_cursor_navigation ~= using_cursor_navigation then
    self._using_cursor_navigation = using_cursor_navigation
    self:_on_navigation_input_changed()
  end

  local category_filter_text = self._category_filter_content.input_text or ""

  if category_filter_text ~= self._applied_category_filter then
    local previous_text = self._applied_category_filter

    self._applied_category_filter = category_filter_text
    self:_on_category_filter_changed(category_filter_text, previous_text)
  end

  local filter_text = self._options_header:filter_text()

  if filter_text ~= self._applied_options_filter then
    local previous_text = self._applied_options_filter

    self._applied_options_filter = filter_text
    self:_on_header_filter_changed(filter_text, previous_text)
  end

  if self:_handling_keybinding() then
    if not drawing_view or not using_cursor_navigation then
      self:close_keybind_popup(true)
    end

    input_service = input_service:null_service()
  end

  self:_handle_keybind_rebind(dt, t, input_service)

  local close_keybind_popup_duration = self._close_keybind_popup_duration

  if close_keybind_popup_duration then
    if close_keybind_popup_duration < 0 then
      self._close_keybind_popup_duration = nil

      self:close_keybind_popup(true)
    else
      self._close_keybind_popup_duration = close_keybind_popup_duration - dt
    end
  end

  local grid_length = self._category_content_grid:length()

  if grid_length ~= self._grid_length then
    self._grid_length = grid_length
  end

  local color_picker_open = self._color_picker ~= nil or self._color_picker_block_input_this_frame
  local selected_category_grid_index = self._category_content_grid:selected_grid_index()

  if not color_picker_open
    and not self._using_cursor_navigation
    and self._selected_navigation_column_index == CATEGORIES_GRID
    and selected_category_grid_index == self._first_category_focusable_index
    and grid_item_is_fully_visible(self._category_content_grid, selected_category_grid_index)
    and input_service:get("navigate_up_continuous") then
    self:_focus_category_filter()
  end

  local category_grid_is_focused = self._selected_navigation_column_index == CATEGORIES_GRID
  local category_filter_blocks_grid = self._category_filter_focused or self:_is_category_filter_writing()
  local category_filter_input_service = color_picker_open and input_service:null_service() or input_service

  FilterInput.update(self._category_filter_content, category_filter_input_service, self._category_filter_focused)

  local category_grid_enabled = category_grid_is_focused and not category_filter_blocks_grid
  local category_grid_input_service = category_grid_enabled and input_service or input_service:null_service()

  local category_grid_service = color_picker_open and input_service:null_service() or category_grid_input_service

  self._category_content_grid:update(dt, t, category_grid_service)

  if not color_picker_open then
    self:_update_category_content_widgets(dt, t)
  end

  local settings_content_grid = self._settings_content_grid

  if settings_content_grid then
    local header_blocks_grid = category_filter_blocks_grid
      or self._header_navigation_control
      or self._options_header:is_filter_writing()

    if not color_picker_open
      and not self._using_cursor_navigation
      and self._selected_navigation_column_index == SETTINGS_GRID
      and not header_blocks_grid
      and not self._selected_settings_widget
      and settings_content_grid:selected_grid_index() == self._first_settings_focusable_index
      and grid_item_is_fully_visible(settings_content_grid, self._first_settings_focusable_index)
      and input_service:get("navigate_up_continuous") then
      self:_focus_header_control("filter")
      input_service = input_service:null_service()
      header_blocks_grid = true
    end

    local settings_grid_enabled = not color_picker_open
      and not category_grid_is_focused
      and not header_blocks_grid
      and not self._selected_settings_widget
    local settings_grid_input_service = settings_grid_enabled and input_service or input_service:null_service()

    settings_content_grid:update(dt, t, settings_grid_input_service)
    self:_update_tab_scroll_animation()

    if not color_picker_open then
      self:_update_settings_content_widgets(dt, t, input_service)
    end
  end

  local header_filter_focused = self._options_header
    and (self._header_navigation_control == "filter" or self._options_header:is_filter_writing())

  if self._category_filter_focused or self:_is_category_filter_writing() or header_filter_focused then
    self.is_text_input_focused = true
  end

  if self._validation_mapping then
    local needs_reset = false
    local reset_all = false

    for category_name, category_data in pairs(self._validation_mapping) do
      local valid = category_data.validation_function and category_data.validation_function()

      if valid ~= nil and valid ~= category_data.validation_result then
        category_data.validation_result = valid
        needs_reset = true

        if reset_all == false then
          reset_all = valid == false and self._selected_category == category_name
        end
      end

      if category_data.settings then
        for _, settings_data in pairs(category_data.settings) do
          valid = settings_data.validation_function and settings_data.validation_function()

          if valid ~= nil and valid ~= settings_data.validation_result then
            settings_data.validation_result = valid
            needs_reset = true
          end
        end
      end
    end

    if needs_reset then
      self:_reset_options_view(reset_all)
    end
  end

  if self._tooltip_data and self._tooltip_data.widget and not self._tooltip_data.widget.content.hotspot.is_hover then
    clear_tooltip(self)
  end

  return DMFOptionsView.super.update(self, dt, t, input_service)
end

DMFOptionsView.on_resolution_modified = function (self)
  DMFOptionsView.super.on_resolution_modified(self)

  local scale = self._render_scale

  self._category_content_grid:on_resolution_modified(scale)

  if self._settings_content_grid then
    self._settings_content_grid:on_resolution_modified(scale)
  end

  if self._options_header then
    self._options_header:invalidate_text_layout()
  end

  load_scrolling_speed_setting()

  self._grid_length = nil
end

DMFOptionsView._on_navigation_input_changed = function (self)
  DMFOptionsView.super._on_navigation_input_changed(self)

  if self._color_picker then
    return
  end

  local selected_color_widget

  for i = 1, #(self._settings_content_widgets or {}) do
    local widget = self._settings_content_widgets[i]
    local content = widget.content
    local on_navigation_input_changed = content.on_navigation_input_changed

    if on_navigation_input_changed then
      on_navigation_input_changed()

      if widget == self._selected_settings_widget then
        selected_color_widget = true
      end
    end
  end

  if selected_color_widget then
    self:_set_exclusive_focus_on_grid_widget(nil)
  end

  if self._using_cursor_navigation then
    self:_clear_header_navigation()
    self:_clear_category_filter_navigation()
  elseif self:_is_category_filter_writing() then
    self:_focus_category_filter()
  elseif self._options_header:is_filter_writing() then
    self:_focus_header_control("filter")
  end

  if self._settings_content_widgets then
    self:_update_grid_navigation_selection()
  end
end

DMFOptionsView._reset_options_view = function (self, reset_all)
  if reset_all then
    self._selected_category = nil
    self._selected_settings_widget = nil
    self._selected_navigation_row_index = nil
    self._selected_navigation_column_index = nil
  end

  self._selected_category_widget = nil

  self:_setup_settings_config(self._options_templates)
  self:_setup_category_config(self._options_templates)

  if self._category_content_widgets then
    self._selected_category = self._selected_category or self._options_templates.categories[1].display_name

    for i = 1, #self._category_content_widgets do
      local widget = self._category_content_widgets[i]
      widget.content.hotspot.is_focused = widget.content.entry.display_name == self._selected_category
      widget.content.hotspot.is_selected = widget.content.entry.display_name == self._selected_category
    end
  end

  self:_update_grid_navigation_selection()
end

DMFOptionsView._refresh_dynamic_options = function (self, changed_entry)
  local category = self._selected_category
  local category_entry = self._selected_category_entry

  if not category or not category_entry then
    return
  end

  local scroll_amount = self:settings_scroll_amount()
  local tab_scroll_offset = self._options_tab_indicator and self._options_tab_indicator:horizontal_scroll_offset()
  local restore_gamepad_focus = not self._using_cursor_navigation
    and self._selected_navigation_column_index == SETTINGS_GRID

  if restore_gamepad_focus and not changed_entry then
    local selected_widget = self._settings_content_widgets[self._selected_navigation_row_index]

    changed_entry = selected_widget and selected_widget.content.entry
  end

  self._close_selected_setting = nil
  clear_tooltip(self)
  self:_set_exclusive_focus_on_grid_widget(nil)
  self:present_category_widgets(category, category_entry, tab_scroll_offset, {
    preserve_header = true,
    restore_saved_scroll = false,
    skip_save_scroll = true,
  })

  local grid = self._settings_content_grid
  local scroll_length = grid:scroll_length()

  if scroll_length > 0 then
    grid:set_scrollbar_progress(math.clamp(scroll_amount, 0, scroll_length) / scroll_length)
    grid:_update_scroll_progress(true)
  end

  if restore_gamepad_focus and changed_entry then
    local category_data = self._settings_category_widgets[category]
    local visible_widgets = {}
    local target_index

    for i = 1, #self._settings_content_widgets do
      visible_widgets[self._settings_content_widgets[i]] = true
    end

    for i = 1, #category_data do
      if category_data[i].entry == changed_entry then
        target_index = i

        break
      end
    end

    while target_index do
      local data = category_data[target_index]
      local content = data.widget.content

      if visible_widgets[data.widget] and (content.hotspot or content.button_hotspot) then
        self:_set_selected_navigation_widget(data.widget)

        break
      end

      local indentation_level = data.entry.indentation_level or 0
      local parent_index

      for i = target_index - 1, 1, -1 do
        if (category_data[i].entry.indentation_level or 0) < indentation_level then
          parent_index = i

          break
        end
      end

      target_index = parent_index
    end
  end
end

DMFOptionsView.settings_grid_length = function (self)
  local grid = self._settings_content_grid

  if grid then
    local scroll_length = grid:scroll_length()
    local total_length = grid:length()
    local area_length = grid:area_length()

    return math.max(total_length - scroll_length, area_length)
  end

  return 0
end

DMFOptionsView.settings_scroll_amount = function (self)
  local grid = self._settings_content_grid

  if grid then
    local scroll_progress = grid:scrollbar_progress()
    local scroll_length = grid:scroll_length()

    return scroll_length * scroll_progress
  end

  return 0
end

DMFOptionsView._selected_category_scroll_offset = function (self, category_entry)
  if category_entry.is_toggle_mods_category then
    return dmf:get(TOGGLE_MODS_SCROLL_OFFSET_SETTING)
  end

  local scroll_offsets = dmf:get(MOD_SCROLL_OFFSETS_SETTING)

  return scroll_offsets[category_entry.mod_name] or 0
end

DMFOptionsView._save_selected_category_scroll_offset = function (self, force)
  local category_entry = self._selected_category_entry

  if not category_entry or not self._settings_content_grid then
    return
  end

  if not force and self._options_header and self._options_header:filter_text() ~= "" then
    return
  end

  local scroll_offset = self:settings_scroll_amount()

  if category_entry.is_toggle_mods_category then
    dmf:set(TOGGLE_MODS_SCROLL_OFFSET_SETTING, scroll_offset)

    return
  end

  local scroll_offsets = dmf:get(MOD_SCROLL_OFFSETS_SETTING)

  scroll_offsets[category_entry.mod_name] = scroll_offset

  dmf:set(MOD_SCROLL_OFFSETS_SETTING, scroll_offsets)
end

DMFOptionsView._restore_selected_category_scroll_offset = function (self, category_entry)
  if not dmf:get("dmf_options_remember_scroll_position") then
    return
  end

  local grid = self._settings_content_grid
  local scroll_length = grid:scroll_length()

  if scroll_length <= 0 then
    return
  end

  local scroll_offset = self:_selected_category_scroll_offset(category_entry)
  local scroll_progress = math.clamp(scroll_offset, 0, scroll_length) / scroll_length

  grid:set_scrollbar_progress(scroll_progress)
end

DMFOptionsView.set_exclusive_focus_on_grid_widget = function (self, widget_name)
  self:_set_exclusive_focus_on_grid_widget(widget_name)
end

DMFOptionsView._handle_input = function (self, input_service)
  if self._color_picker or self._color_picker_block_input_this_frame then
    return
  end

  local selected_settings_widget = self._selected_settings_widget

  if selected_settings_widget then
    local content = selected_settings_widget.content
    local gamepad_input_handler = not self._using_cursor_navigation and content.gamepad_input_handler

    if gamepad_input_handler then
      self._close_selected_setting = gamepad_input_handler(input_service) and true or nil

      return
    end

    local scrollbar_hotspot = content.scrollbar_hotspot
    local input_hotspot = content.input_hotspot
    local has_selected_text = content.selected_text and content.selected_text ~= ""
    local input_hotspot_active = input_hotspot
      and input_hotspot.is_hover
      and (not content.is_writing or has_selected_text)
    local selected_control_active = content.drag_active
      or (scrollbar_hotspot and scrollbar_hotspot.is_hover)
      or input_hotspot_active
    local close_selected_setting = false

    local clicked_away = input_service:get("left_pressed") and not selected_control_active
    local confirmed = input_service:get("confirm_pressed")
    local cancelled = input_service:get("back")

    if clicked_away or confirmed or cancelled then
      close_selected_setting = true
    else
      self._navigation_column_changed_this_frame = false
    end

    self._close_selected_setting = close_selected_setting
  elseif self._category_filter_focused then
    self:_handle_category_filter_navigation(input_service)
  elseif self._header_navigation_control then
    self:_handle_header_navigation(input_service)
  else
    local selected_navigation_row = self._selected_navigation_row_index
    local selected_navigation_column = self._selected_navigation_column_index

    if selected_navigation_row and selected_navigation_column then
      local can_page_tabs = not self._using_cursor_navigation and selected_navigation_column == SETTINGS_GRID

      if can_page_tabs and input_service:get("navigate_primary_left_pressed") then
        self:_page_options_tab(-1)
      elseif can_page_tabs and input_service:get("navigate_primary_right_pressed") then
        self:_page_options_tab(1)
      elseif input_service:get("navigate_left_continuous") then
        self:_change_navigation_column(selected_navigation_column - 1)
      elseif input_service:get("navigate_right_continuous") then
        self:_change_navigation_column(selected_navigation_column + 1)
      elseif not input_service:get("confirm_pressed") and not input_service:get("back") then
        self._navigation_column_changed_this_frame = false
      end
    elseif not input_service:get("confirm_pressed") and not input_service:get("back") then
      self._navigation_column_changed_this_frame = false
    end
  end
end

DMFOptionsView.show_color_picker = function (self, entry)
  if self._color_picker or entry.disabled then
    return
  end

  local color = entry.get_function() or entry.default_value
  clear_tooltip(self)
  self:_set_exclusive_focus_on_grid_widget(nil)
  self._color_picker = self:_add_element(ViewElementColorPicker, "color_picker", 100, {
    color = color,
    entry = entry,
  })
  self._color_picker_block_input_this_frame = true
  self:set_can_exit(false)
end

DMFOptionsView.update_color_widget_preview = function (self, entry, color)
  local widgets = self._settings_content_widgets or {}

  for i = 1, #widgets do
    local content = widgets[i].content

    if content.entry == entry then
      local preview_color = content.preview_color

      for channel = 1, 4 do
        preview_color[channel] = color[channel]
      end

      content.color_value_text_dirty = true

      return
    end
  end
end

DMFOptionsView.close_color_picker = function (self)
  if self._color_picker then
    self:_remove_element("color_picker")
    self._color_picker = nil
    self._color_picker_closed_this_frame = true
    self._color_picker_block_input_this_frame = true
    self:set_can_exit(true, true)
    self:_update_grid_navigation_selection()
  end
end

DMFOptionsView._update_grid_navigation_selection = function (self)
  if self._category_filter_focused or self._header_navigation_control then
    return
  end

  local selected_column_index = self._selected_navigation_column_index
  local selected_row_index = self._selected_navigation_row_index

  if self._using_cursor_navigation then
    if selected_row_index or selected_column_index then
      self:_set_selected_navigation_widget(nil)
    end
  else
    local navigation_widgets = self._navigation_widgets[selected_column_index]
    local selected_widget = navigation_widgets and navigation_widgets[selected_row_index] or self._selected_settings_widget

    if selected_widget then
      local selected_grid = self._navigation_grids[selected_column_index]

      if not selected_grid or not selected_grid:selected_grid_index() then
        self:_set_selected_navigation_widget(selected_widget)
      end
    elseif navigation_widgets or self._settings_content_widgets then
      self:_set_default_navigation_widget()
    end
    -- Removed extra condition for default category - moved to on_view_load_complete
  end
end

DMFOptionsView.present_category_widgets = function (self, category, category_entry, tab_scroll_offset, presentation)
  presentation = presentation or {}

  if not presentation.skip_save_scroll then
    self:_save_selected_category_scroll_offset()
  end

  self._tab_scroll_animation = nil
  local category_changed = self._selected_category ~= category or self._selected_category_entry ~= category_entry

  if category_changed and not presentation.preserve_header then
    self:_clear_header_navigation()
    local header_height, header_spacing = self._options_header:set_category(category_entry)

    self._settings_header_height = header_height
    self._settings_header_spacing = header_spacing
    self._applied_options_filter = ""
  end

  self._selected_category = category
  self._selected_category_entry = category_entry
  local settings_category_widgets = self._settings_category_widgets
  local category_data = settings_category_widgets[category]

  if category_data then
    dmf:set("options_menu_last_selected", category)
    clear_tooltip(self)
    self:_remove_options_tab_indicator()
    self:_set_options_header_layout(self._settings_header_height, self._settings_header_spacing, false)

    local include_ids = category_entry.is_toggle_mods_category or dmf:get(SHOW_MOD_OPTION_IDS_SETTING)
    local grid_data = OptionsFilter.filter(category_data, self._options_header:filter_text(), include_ids)
    local widgets = {}
    local alignment_widgets = {}

    for i = 1, #grid_data do
      local data = grid_data[i]
      local alignment_widget = data.alignment_widget
      local spacing_before = alignment_widget.spacing_before

      widgets[#widgets + 1] = data.widget

      if spacing_before and #alignment_widgets > 0 then
        alignment_widget = table.clone(alignment_widget)
        alignment_widget.size = table.clone(alignment_widget.size)
        alignment_widget.size[2] = alignment_widget.size[2] + spacing_before
        alignment_widget.vertical_alignment = "bottom"
      end

      alignment_widgets[#alignment_widgets + 1] = alignment_widget
    end

    self._settings_content_widgets = widgets
    self._settings_alignment_list = alignment_widgets
    local scrollbar_widget_id = "settings_scrollbar"
    local grid_scenegraph_id = "settings_grid_background"
    local grid_pivot_scenegraph_id = "settings_grid_content_pivot"
    local grid_spacing = _view_settings.settings_grid_spacing
    self._settings_content_grid = self:_setup_grid(self._settings_content_widgets, self._settings_alignment_list, grid_scenegraph_id, grid_spacing, false)

    self:_setup_content_grid_scrollbar(self._settings_content_grid, scrollbar_widget_id, grid_scenegraph_id, grid_pivot_scenegraph_id)

    self:_setup_options_tab_indicator(grid_data, category_entry, tab_scroll_offset)

    if presentation.restore_saved_scroll ~= false and self._options_header:filter_text() == "" then
      self:_restore_selected_category_scroll_offset(category_entry)
    end

    self._navigation_widgets[SETTINGS_GRID] = widgets
    self._navigation_grids[SETTINGS_GRID] = self._settings_content_grid
    self._first_settings_focusable_widget = nil
    self._first_settings_focusable_index = nil

    for i = 1, #widgets do
      local content = widgets[i].content

      if content.hotspot or content.button_hotspot then
        self._first_settings_focusable_widget = widgets[i]
        self._first_settings_focusable_index = i

        break
      end
    end

    if not self._header_navigation_control then
      self:_update_grid_navigation_selection()
    end
  end
end

DMFOptionsView._clear_header_navigation = function (self)
  self._header_navigation_control = nil

  if self._options_header then
    self._options_header:set_focused_control(nil)
  end
end

DMFOptionsView._is_category_filter_writing = function (self)
  return self._category_filter_content and self._category_filter_content.is_writing
end

DMFOptionsView._clear_category_filter_navigation = function (self)
  self._category_filter_focused = nil

  if self._category_filter_content then
    FilterInput.set_focused(self._category_filter_content, false)
  end
end

DMFOptionsView._focus_category_filter = function (self)
  self:_set_selected_navigation_widget(nil)
  self:_clear_header_navigation()

  self._category_filter_focused = true

  FilterInput.set_focused(self._category_filter_content, true)
end

DMFOptionsView._category_focus_widget = function (self)
  local selected_widget = self._selected_category_widget
  local widgets = self._category_content_widgets

  for i = 1, #widgets do
    if widgets[i] == selected_widget then
      return selected_widget
    end
  end

  return self._first_category_focusable_widget
end

DMFOptionsView._focus_first_category_from_filter = function (self)
  local widget = self:_category_focus_widget()

  if widget then
    self:_set_selected_navigation_widget(widget)
  end
end

DMFOptionsView._handle_category_filter_navigation = function (self, input_service)
  if self:_is_category_filter_writing() then
    return
  end

  if input_service:get("navigate_down_continuous") then
    self:_focus_first_category_from_filter()
  elseif input_service:get("navigate_right_continuous") then
    self:_change_navigation_column(SETTINGS_GRID)
  elseif not input_service:get("confirm_pressed") and not input_service:get("back") then
    self._navigation_column_changed_this_frame = false
  end
end

DMFOptionsView._focus_header_control = function (self, control)
  if control == "toggle" and not self._options_header:has_toggle() then
    control = "filter"
  elseif control == "pin" and not self._options_header:has_pin() then
    control = nil
  end

  self:_set_selected_navigation_widget(nil)
  self:_clear_category_filter_navigation()
  self._header_navigation_control = control
  self._options_header:set_focused_control(control)
end

DMFOptionsView._focus_category_from_header = function (self)
  local category_widget = self:_category_focus_widget()

  if category_widget then
    self:_set_selected_navigation_widget(category_widget)
  else
    self:_focus_category_filter()
  end
end

DMFOptionsView._focus_first_setting_from_header = function (self)
  local widget = focusable_widget_at_scroll_position(
    self._navigation_widgets[SETTINGS_GRID],
    self._navigation_grids[SETTINGS_GRID]
  )

  if widget then
    self:_set_selected_navigation_widget(widget)
  end
end

DMFOptionsView._handle_header_navigation = function (self, input_service)
  local control = self._header_navigation_control

  if self._options_header:is_filter_writing() then
    return
  end

  if input_service:get("navigate_left_continuous") then
    if control ~= "pin" and self._options_header:has_pin() then
      self:_focus_header_control("pin")
    else
      self:_focus_category_from_header()
    end
  elseif control == "pin" then
    if input_service:get("navigate_right_continuous") then
      self:_focus_header_control(self._options_header:has_toggle() and "toggle" or "filter")
    elseif input_service:get("navigate_down_continuous") then
      self:_focus_first_setting_from_header()
    end
  elseif control == "toggle" then
    if input_service:get("navigate_down_continuous") then
      self:_focus_header_control("filter")
    end
  elseif control == "filter" then
    if input_service:get("navigate_up_continuous") and self._options_header:has_toggle() then
      self:_focus_header_control("toggle")
    elseif input_service:get("navigate_down_continuous") then
      self:_focus_first_setting_from_header()
    end
  end
end

DMFOptionsView._on_header_filter_changed = function (self, filter_text, previous_text)
  if not self._selected_category or not self._selected_category_entry then
    return
  end

  if previous_text == "" and filter_text ~= "" then
    self:_save_selected_category_scroll_offset(true)
  end

  local tab_scroll_offset = self._options_tab_indicator and self._options_tab_indicator:horizontal_scroll_offset()

  self:present_category_widgets(self._selected_category, self._selected_category_entry, tab_scroll_offset, {
    preserve_header = true,
    restore_saved_scroll = filter_text == "",
    skip_save_scroll = true,
  })
end

DMFOptionsView._setup_category_config = function (self, config)
  if self._all_category_content_widgets then
    for i = 1, #self._all_category_content_widgets do
      local widget = self._all_category_content_widgets[i]

      self:_unregister_widget_name(widget.name)
    end

    self._all_category_content_widgets = nil
  end

  local config_categories = config.categories or {}
  local entries = {}
  local reset_functions_by_category = {}
  local categories_by_display_name = {}

  for i = 1, #config_categories do
    local category_config = config_categories[i]
    local category_display_name = category_config.display_name
    local category_reset_function = category_config.reset_function
    local valid = self._validation_mapping[category_display_name].validation_result

    if valid then
      local entry = {
        widget_type = "settings_button",
        original_index = i,
        description = category_config.description,
        display_name = category_display_name,
        version = category_config.version,
        author = category_config.author,
        can_be_reset = category_config.can_be_reset,
        is_favorited = category_config.is_favorited,
        is_togglable = category_config.is_togglable,
        mod_name = category_config.mod_name,
        search_id = category_config.mod_name,
        is_toggle_mods_category = category_config.is_toggle_mods_category,
        pressed_function = function (parent, widget, entry)
          self._selected_category_widget = widget
          self._category_content_grid:select_widget(widget)

          self:present_category_widgets(category_display_name, entry)

          local selected_navigation_column = self._selected_navigation_column_index

          if selected_navigation_column then
            self:_change_navigation_column(selected_navigation_column + 1)
          end
        end,
        select_function = function (parent, widget, entry)
          self:present_category_widgets(category_display_name, entry)
        end
      }
      entries[#entries + 1] = entry
      categories_by_display_name[category_display_name] = entry
      reset_functions_by_category[category_display_name] = category_reset_function
    end
  end

  sort_pinned_categories(entries)

  -- Retrieve default category from settings
  local category_setting = dmf:get("options_menu_last_selected")
  if category_setting and not categories_by_display_name[category_setting] then
    category_setting = false
  end

  self._default_category = category_setting or (
    config_categories[1] and config_categories[1].display_name
  )

  local scenegraph_id = "grid_content_pivot"
  local callback_name = "cb_on_category_pressed"
  local widgets, alignment_widgets = self:_setup_content_widgets(entries, scenegraph_id, callback_name)
  local category_data = {}

  for i = 1, #widgets do
    category_data[i] = {
      entry = entries[i],
      widget = widgets[i],
      alignment_widget = alignment_widgets[i],
    }
    update_category_pin_display(category_data[i])
  end

  self._all_category_content_widgets = widgets
  self._category_data = category_data
  self._navigation_widgets = {}
  self._navigation_grids = {}

  OptionsFilter.prepare(category_data)
  self:_present_category_filter(self._category_filter_content.input_text or "", _last_selected_category_widget)

  self._reset_functions_by_category = reset_functions_by_category
  self._categories_by_display_name = categories_by_display_name
end

DMFOptionsView._present_category_filter = function (
  self, filter_text, category_position_widget, initial_scroll_progress
)
  clear_tooltip(self)

  local grid_data = OptionsFilter.filter(self._category_data, filter_text, true)
  local widgets = {}
  local alignment_widgets = {}

  for i = 1, #grid_data do
    local data = grid_data[i]

    widgets[i] = data.widget
    alignment_widgets[i] = data.alignment_widget
  end

  self._category_content_widgets = widgets
  self._category_alignment_list = alignment_widgets

  local scrollbar_widget_id = "scrollbar"
  local grid_scenegraph_id = "background"
  local grid_pivot_scenegraph_id = "grid_content_pivot"
  local grid_spacing = _view_settings.category_grid_spacing
  self._category_content_grid = self:_setup_grid(widgets, alignment_widgets, grid_scenegraph_id, grid_spacing, true)

  self:_setup_content_grid_scrollbar(
    self._category_content_grid,
    scrollbar_widget_id,
    grid_scenegraph_id,
    grid_pivot_scenegraph_id,
    category_position_widget,
    initial_scroll_progress
  )

  self._navigation_widgets[CATEGORIES_GRID] = widgets
  self._navigation_grids[CATEGORIES_GRID] = self._category_content_grid
  self._first_category_focusable_widget = widgets[1]
  self._first_category_focusable_index = widgets[1] and 1 or nil

  if not self._using_cursor_navigation
    and self._selected_navigation_column_index == CATEGORIES_GRID
    and not self._category_filter_focused then
    local widget = self:_category_focus_widget()

    if widget then
      self:_set_selected_navigation_widget(widget)
    else
      self:_focus_category_filter()
    end
  end
end

DMFOptionsView._on_category_filter_changed = function (self, filter_text, previous_text)
  local category_position_widget = previous_text ~= "" and filter_text == ""
    and self._selected_category_widget
    or nil

  self:_present_category_filter(filter_text, category_position_widget)
end

DMFOptionsView._setup_settings_config = function (self, config)
  if self._settings_category_widgets then
    for _, settings_data in pairs(self._settings_category_widgets) do
      for i = 1, #settings_data do
        local widget = settings_data[i].widget

        self:_unregister_widget_name(widget.name)
      end
    end

    self._settings_category_widgets = {}
  end

  local config_settings = config.settings
  local category_widgets = {}
  local settings_default_values = {}
  local aligment_list = {}
  local callback_name = "cb_on_settings_pressed"
  local changed_callback_name = "cb_on_settings_changed"

  for setting_index, setting in ipairs(config_settings) do
    local valid = self._validation_mapping[setting.category].settings[setting.display_name].validation_result
    local category = setting.category or "Uncategorized"

    if valid then
      if not settings_default_values[category] then
        settings_default_values[category] = {}
      end

      if setting.get_function then
        settings_default_values[category][setting] = setting.default_value
      end

      local widgets = category_widgets[category]

      if not widgets then
        widgets = {}
        category_widgets[category] = widgets
      end

      local widget_suffix = "setting_" .. tostring(setting_index)
      local widget, alignment_widget = self:_create_settings_widget_from_config(setting, category, widget_suffix, callback_name, changed_callback_name)
      widgets[#widgets + 1] = {
        entry = setting,
        widget = widget,
        alignment_widget = alignment_widget
      }
    end
  end

  for i = 1, #(config.categories or {}) do
    local category = config.categories[i].display_name

    category_widgets[category] = category_widgets[category] or {}
    settings_default_values[category] = settings_default_values[category] or {}
  end

  for _, category_data in pairs(category_widgets) do
    OptionsFilter.prepare(category_data)
  end

  self._settings_category_default_values = settings_default_values
  self._settings_category_widgets = category_widgets
end

DMFOptionsView._remove_options_tab_indicator = function (self)
  if self._options_tab_indicator then
    self:_remove_element("options_tab_indicator")
    self._options_tab_indicator = nil
  end
end

DMFOptionsView._setup_options_tab_indicator = function (self, grid_data, category_entry, tab_scroll_offset)
  local first_option_index = #grid_data > 0 and 1 or nil

  if not first_option_index then
    return
  end

  local function first_focusable_widget(start_index, end_index)
    for i = start_index, end_index do
      local widget = grid_data[i].widget
      local content = widget and widget.content

      if content and (content.hotspot or content.button_hotspot) then
        return widget, i
      end
    end
  end

  local function first_focusable_descendant(start_index)
    local end_index = #grid_data

    for i = start_index + 1, #grid_data do
      if (grid_data[i].entry.indentation_level or 0) == 0 then
        end_index = i - 1

        break
      end
    end

    return first_focusable_widget(start_index + 1, end_index)
  end

  local candidates = {}

  for i = first_option_index, #grid_data do
    local data = grid_data[i]
    local entry = data.entry

    if entry.is_options_tab_candidate then
      local focus_widget = data.widget
      local focus_grid_index = i

      if not entry.options_tab_focus_self then
        focus_widget, focus_grid_index = first_focusable_descendant(i)
      end

      candidates[#candidates + 1] = {
        display_name = entry.display_name,
        focus_grid_index = focus_grid_index,
        focus_widget = focus_widget,
        start_index = i,
      }
    end
  end

  local valid_candidates = {}

  for i = 1, #candidates do
    local candidate = candidates[i]

    if candidate.focus_widget then
      valid_candidates[#valid_candidates + 1] = candidate
    end
  end

  if not valid_candidates[1] or valid_candidates[1].start_index ~= first_option_index then
    table.insert(valid_candidates, 1, {
      display_name = category_entry.display_name,
      is_mod_tab = true,
      start_index = first_option_index,
    })
  end

  -- Only reserve tab space when the full-height grid already needs scrolling.
  local base_scroll_length = self._settings_content_grid:scroll_length()
  local tabs = {}

  for i = 1, #valid_candidates do
    local candidate = valid_candidates[i]
    local end_index = i < #valid_candidates and valid_candidates[i + 1].start_index - 1 or #grid_data
    local focus_widget = candidate.focus_widget
    local focus_grid_index = candidate.focus_grid_index

    if candidate.is_mod_tab then
      focus_widget, focus_grid_index = first_focusable_widget(candidate.start_index, end_index)
    end

    if focus_widget then
      local first_widget = grid_data[candidate.start_index].widget
      local last_widget = grid_data[end_index].widget

      tabs[#tabs + 1] = {
        content_end = math.abs(last_widget.offset[2]) + last_widget.content.size[2],
        content_start = math.abs(first_widget.offset[2]),
        display_name = candidate.display_name,
        focus_grid_index = focus_grid_index,
        focus_widget = focus_widget,
        scroll_offset = math.abs(first_widget.offset[2]),
      }
    end
  end

  if #tabs <= 1 or base_scroll_length <= 0 then
    return
  end

  self:_set_options_header_layout(self._settings_header_height, self._settings_header_spacing, true)
  self._settings_content_grid:on_resolution_modified(self._render_scale)
  update_scroll_amount(self._widgets_by_name.settings_scrollbar)

  local scroll_length = self._settings_content_grid:scroll_length()

  for i = 1, #tabs do
    tabs[i].scroll_offset = math.min(tabs[i].scroll_offset, scroll_length)
  end

  tabs[1].scroll_offset = 0

  local layout = self._settings_grid_layout
  local settings_grid_scenegraph = self._ui_scenegraph.settings_grid_background

  self._options_tab_indicator = self:_add_element(ViewElementOptionsTabIndicator, "options_tab_indicator", 20, {
    available_width = settings_grid_scenegraph.size[1],
    available_x = settings_grid_scenegraph.world_position[1],
    initial_scroll_offset = tab_scroll_offset,
    panel_y = layout.header_y + self._settings_header_height + layout.tab_spacing,
    tabs = tabs,
    get_focused_grid_index = callback(self, "_focused_options_grid_index"),
    get_scroll_amount = callback(self, "settings_scroll_amount"),
    on_tab_pressed = callback(self, "_on_options_tab_pressed"),
    show_gamepad_prompts = callback(self, "_show_options_tab_gamepad_prompts"),
  })
end

DMFOptionsView._focused_options_grid_index = function (self)
  return self._selected_navigation_column_index == SETTINGS_GRID and self._selected_navigation_row_index or nil
end

DMFOptionsView._show_options_tab_gamepad_prompts = function (self)
  return not self._using_cursor_navigation
    and self._selected_navigation_column_index == SETTINGS_GRID
    and not self._selected_settings_widget
    and not self._color_picker
end

DMFOptionsView._page_options_tab = function (self, direction)
  local tab_indicator = self._options_tab_indicator

  if not tab_indicator then
    return
  end

  local tab, tab_index = tab_indicator:relative_tab(direction, self._selected_navigation_row_index)

  if not tab then
    return
  end

  local scroll_amount = self:settings_scroll_amount()
  local visible_end = scroll_amount + self._settings_content_grid:area_length()
  local tab_fully_visible = scroll_amount <= tab.content_start and tab.content_end <= visible_end

  if tab.focus_widget then
    self:_set_selected_navigation_widget(tab.focus_widget)
  end

  tab_indicator:select_focused_tab(tab_index)

  if not tab_fully_visible then
    self:_on_options_tab_pressed(tab)
  end
end

DMFOptionsView._on_options_tab_pressed = function (self, tab)
  local grid = self._settings_content_grid
  local scroll_length = grid:scroll_length()
  local scroll_progress = scroll_length > 0 and tab.scroll_offset / scroll_length or 0

  grid:set_scrollbar_progress(scroll_progress, true)

  local scrollbar_content = self._widgets_by_name.settings_scrollbar.content

  scrollbar_content.scroll_add = nil
  scrollbar_content.scroll_value = nil
  self._tab_scroll_animation = true
end

DMFOptionsView._update_tab_scroll_animation = function (self)
  if not self._tab_scroll_animation then
    return
  end

  local grid = self._settings_content_grid
  local scrollbar_content = self._widgets_by_name.settings_scrollbar.content

  if grid._ui_animations.scrollbar then
    scrollbar_content.scroll_value = nil
  else
    scrollbar_content.scroll_value = scrollbar_content.value
    self._tab_scroll_animation = nil
  end
end

DMFOptionsView._update_category_content_widgets = function (self, dt, t)
  local category_content_widgets = self._category_content_widgets

  if category_content_widgets then
    local focused_widget_index = not self._using_cursor_navigation
      and self._category_content_grid:selected_grid_index()

    if focused_widget_index then
      self._selected_navigation_row_index = focused_widget_index
      self._selected_navigation_column_index = CATEGORIES_GRID
    end

    local is_focused_grid = not self._using_cursor_navigation
      and self._selected_navigation_column_index == CATEGORIES_GRID
    local selected_category_widget = self._selected_category_widget

    for i = 1, #category_content_widgets do
      local widget = category_content_widgets[i]
      local hotspot = widget.content.hotspot

      if hotspot.is_focused then
        hotspot.is_selected = true

        if widget ~= selected_category_widget then
          self._selected_category_widget = widget
          local entry = widget.content.entry

          if entry and entry.select_function then
            entry.select_function(self, widget, entry)
          end
        end
      elseif is_focused_grid then
        hotspot.is_selected = false
      end
    end
  end
end

DMFOptionsView._set_tooltip_data = function (self, widget, identifier_text)
  identifier_text = identifier_text or ""

  local current_widget = self._tooltip_data and self._tooltip_data.widget
  local current_identifier = self._tooltip_data and self._tooltip_data.identifier
  local localized_text = nil
  local entry = widget.content.entry
  local tooltip_text = entry.tooltip_text
  local disabled_by_list = entry.disabled_by

  if tooltip_text then
    if type(tooltip_text) == "function" then
      localized_text = tooltip_text()
    else
      -- Should already be localized in mod option generation
      localized_text = tooltip_text
    end
  end

  if disabled_by_list then
    localized_text = localized_text and string.format("%s\n", localized_text)

    for _, text in pairs(disabled_by_list) do
      localized_text = localized_text and string.format("%s\n%s", localized_text, text) or text
    end
  end

  local starting_point = self:_scenegraph_world_position("settings_grid_start")
  local current_y = self._widgets_by_name.tooltip.offset[2]
  local scroll_addition = self._settings_content_grid:length_scrolled()
  local new_y = starting_point[2] + widget.offset[2] - scroll_addition

  if current_widget ~= widget or new_y ~= current_y or identifier_text ~= current_identifier then
    local tooltip = self._widgets_by_name.tooltip
    local metadata_text = entry.tooltip_metadata or ""

    self._tooltip_data = {
      identifier = identifier_text,
      widget = widget,
      text = localized_text,
    }
    tooltip.content.identifier_text = identifier_text
    tooltip.content.metadata_text = metadata_text
    tooltip.content.text = localized_text or ""

    local x_pos = starting_point[1] + widget.offset[1]
    local text_width = widget.content.size[1] * 0.5
    local horizontal_inset = TOOLTIP_HORIZONTAL_PADDING * 0.5
    local vertical_inset = TOOLTIP_VERTICAL_PADDING * 0.5
    local width = text_width + TOOLTIP_HORIZONTAL_PADDING
    local y_offset = vertical_inset
    local text_layouts = {
      { identifier_text, tooltip.style.identifier_text },
      { metadata_text, tooltip.style.metadata_text },
      { tooltip.content.text, tooltip.style.text },
    }

    for i = 1, #text_layouts do
      local text = text_layouts[i][1]
      local style = text_layouts[i][2]

      if text ~= "" then
        local _, text_height = self:_text_size(text, style, {
          text_width,
          TOOLTIP_TEXT_HEIGHT_BOUND,
        }, true)

        text_height = math.ceil(text_height)
        style.offset[1] = horizontal_inset
        style.offset[2] = y_offset
        style.size = { text_width, text_height }
        y_offset = y_offset + text_height + TOOLTIP_SECTION_SPACING
      else
        style.size = { text_width, 0 }
      end
    end

    local height = math.max(
      y_offset - TOOLTIP_SECTION_SPACING + vertical_inset,
      TOOLTIP_VERTICAL_PADDING
    )

    tooltip.content.size = {
      width,
      height,
    }
    tooltip.offset[1] = x_pos - width * 0.8
    tooltip.offset[2] = math.max(new_y - height, 20)
    tooltip.content.visible = true
  end
end

DMFOptionsView._update_settings_content_widgets = function (self, dt, t, input_service)
  local settings_content_widgets = self._settings_content_widgets

  if settings_content_widgets then
    local focused_widget_index = self._settings_content_grid:selected_grid_index()
    local focused_widget = focused_widget_index and settings_content_widgets[focused_widget_index]

    if focused_widget then
      self:_set_selected_navigation_widget(focused_widget)
    end

    local handle_input = false
    local selected_settings_widget = self._selected_settings_widget

    self.is_text_input_focused = false

    for i = 1, #settings_content_widgets do
      local widget = settings_content_widgets[i]
      local widget_type = widget.type
      local template = _content_blueprints[widget_type]
      local update = template and template.update

      if update then
        update(self, widget, input_service, dt, t)
      end
    end

    local dynamic_options_changed_entry = self._dynamic_options_changed_entry

    if dynamic_options_changed_entry then
      self._dynamic_options_changed_entry = nil
      self:_refresh_dynamic_options(dynamic_options_changed_entry)

      return
    end

    if selected_settings_widget and self._close_selected_setting then
      self:_set_exclusive_focus_on_grid_widget(nil)
      self:_update_grid_navigation_selection()

      self._close_selected_setting = nil
    end
  end
end

DMFOptionsView._create_settings_widget_from_config = function (self, config, category, suffix, callback_name, changed_callback_name)
  local scenegraph_id = "settings_grid_content_pivot"
  local default_value = config.default_value
  local default_value_type = type(default_value)
  local options = config.options or config.options_function and config.options_function()
  local widget_type = config.widget_type

  if not widget_type then
    if options then
      widget_type = "dropdown"
    else
      local get_function = config.get_function

      if get_function then
        local value = get_function(config)
        local value_type = value ~= nil and type(value) or default_value_type

        if value_type == "boolean" then
          widget_type = "checkbox"
        elseif value_type == "number" then
          widget_type = "value_slider"
        elseif value_type == "string" then
          widget_type = "settings_button"
        else
          widget_type = "settings_button"
        end
      end
    end
  end

  if widget_type == "button" then
    config.ignore_focus = true
  end

  local widget = nil
  local template = _content_blueprints[widget_type]
  local size = template.size_function and template.size_function(self, config) or template.size
  local indentation_level = config.indentation_level or 0
  local indentation_spacing = _view_settings.indentation_spacing * indentation_level
  local new_size = {
    size[1] - indentation_spacing,
    size[2]
  }
  local pass_template_function = template.pass_template_function
  local pass_template = pass_template_function and pass_template_function(self, config, new_size) or template.pass_template
  local widget_definition = pass_template and UIWidget.create_definition(pass_template, scenegraph_id, nil, new_size)
  local name = "widget_" .. suffix

  if widget_definition then
    widget = self:_create_widget(name, widget_definition)
    widget.type = widget_type
    local init = template.init

    if init then
      init(self, widget, config, callback_name, changed_callback_name)
    end
  end

  if widget then
    return widget, {
      horizontal_alignment = "right",
      spacing_before = template.spacing_before,
      size = size,
      name = name
    }
  else
    return nil, {
      size = size
    }
  end
end

DMFOptionsView._handle_keybind_rebind = function (self, dt, t, input_service)
  if self._handling_keybind then
    local input_manager = Managers.input
    local results = input_manager:key_watch_result()

    if results then
      local entry = self._active_keybind_entry
      local widget = self._active_keybind_widget
      local presentation_string = InputUtils.localized_string_from_key_info(results)
      local service_type = entry.service_type
      local alias_name = entry.alias_name
      local value = entry.value
      local can_close = entry.on_activated(results, value)

      if can_close then
        self:close_keybind_popup()
      else
        Managers.input:stop_key_watch()

        local devices = entry.devices

        Managers.input:start_key_watch(devices)
      end
    end
  end
end

DMFOptionsView._handling_keybinding = function (self)
  return self._handling_keybind or self._close_keybind_popup_duration ~= nil
end

DMFOptionsView._present_keybind_popup_grid = function (self, display_name, value, cancel_keys)
  local popup = self._keybind_popup
  local definitions = popup._definitions
  local grid_scenegraph = definitions.scenegraph_definition.text_box
  local grid_size = grid_scenegraph.size
  local layout = {
    {
      widget_type = "header",
      text = display_name,
    },
    {
      widget_type = "dynamic_spacing",
      size = {
        grid_size[1],
        15,
      },
    },
  }

  if cancel_keys then
    local cancel_key = cancel_keys[1]
    local description_text = Localize("loc_setting_keybinding_press_new_button", true, {
      cancel_input = InputUtils.key_axis_locale(cancel_key),
    })

    layout[#layout + 1] = {
      widget_type = "description",
      text = description_text,
    }
    layout[#layout + 1] = {
      widget_type = "dynamic_spacing",
      size = {
        grid_size[1],
        10,
      },
    }
  end

  layout[#layout + 1] = {
    widget_type = "value",
    text = value and InputUtils.localized_string_from_key_info(value) or self:_localize("loc_keybind_unassigned"),
  }

  popup._text_grid:present_grid_layout(layout, definitions.grid_blueprints, nil, nil, nil, nil, callback(popup, "cb_on_grid_layout_changed"), nil)
end

DMFOptionsView.show_keybind_popup = function (self, widget, entry)
  if not self:_handling_keybinding() then
    self._active_keybind_entry = entry
    self._active_keybind_widget = widget
    local layer = 100
    local reference_name = "keybind_popup"
    self._keybind_popup = self:_add_element(ViewElementKeybindPopup, reference_name, layer)
    local display_name = entry.display_name or self:_localize("loc_settings_option_unavailable")
    local value = entry:get_function()
    local devices = entry.devices

    self:_present_keybind_popup_grid(display_name, value, entry.cancel_keys)
    Managers.input:start_key_watch(devices)

    self._handling_keybind = true

    self:set_can_exit(false)
  end
end

DMFOptionsView.close_keybind_popup = function (self, force_close)
  if force_close then
    Managers.input:stop_key_watch()

    local reference_name = "keybind_popup"
    self._keybind_popup = nil

    self:_remove_element(reference_name)
    self:set_can_exit(true, true)
  else
    self._close_keybind_popup_duration = 0.2
  end

  self._handling_keybind = false
  self._active_keybind_entry = nil
  self._active_keybind_widget = nil
end

DMFOptionsView._set_warning_text = function (self)
  local widgets_by_name = self._widgets_by_name
  local warning_text = widgets_by_name.warning_text
  local action = "TEST"
  local color_1 = self:_get_color_string_by_color(Color.ui_brown_light(255, true))
  local color_2 = self:_get_color_string_by_color(Color.red(255, true))
  warning_text.content.text = string.format("Warning! Input for action %s%s%s has been unassigned.", color_1, action, color_2)
end

DMFOptionsView.cb_on_category_pressed = function (self, widget, entry)
  local pressed_function = entry.pressed_function

  if pressed_function then
    pressed_function(self, widget, entry)
  end
end

DMFOptionsView.cb_on_settings_pressed = function (self, widget, entry)
  if not self._can_close or self._selected_settings_widget or self._navigation_column_changed_this_frame then
    return
  end

  local pressed_function = entry.pressed_function

  if pressed_function then
    pressed_function(self, widget, entry)
  end

  if not entry.ignore_focus then
    local widget_name = widget.name
    local selected_widget = self:_set_exclusive_focus_on_grid_widget(widget_name)
    selected_widget.offset[3] = selected_widget and 90 or 0
  end
end

DMFOptionsView.cb_on_settings_changed = function (self, widget, entry, option_value)
  if entry.setting_id == SHOW_MOD_OPTION_IDS_SETTING and self._options_header:filter_text() ~= "" then
    self._applied_options_filter = nil
  end

  if not self._require_restart and setting_requires_restart(entry, option_value) then
    self._require_restart = true
  end

  if entry.controls_sub_widgets then
    self:cb_on_dynamic_setting_value_changed(widget, entry, option_value)
  end
end

DMFOptionsView.cb_on_dynamic_setting_value_changed = function (self, widget, entry, option_value)
  if widget then
    widget.content.dynamic_visibility_value = option_value
  end

  if dmf:update_mod_options_visibility(self._options_templates, entry.mod_name) then
    self._dynamic_options_changed_entry = entry
  end
end

DMFOptionsView._enable_settings_overlay = function (self, enable)
  local widgets_by_name = self._widgets_by_name
  local settings_overlay_widget = widgets_by_name.settings_overlay
  settings_overlay_widget.content.visible = enable
end

DMFOptionsView._set_exclusive_focus_on_grid_widget = function (self, widget_name)
  local widgets = self._settings_content_widgets
  local selected_widget = nil

  for i = 1, #widgets do
    local widget = widgets[i]
    local selected = widget.name == widget_name
    local content = widget.content
    content.exclusive_focus = selected
    local hotspot = content.hotspot or content.button_hotspot

    if hotspot then
      hotspot.is_selected = selected

      if selected then
        selected_widget = widget
      end
    end
  end

  self._selected_settings_widget = selected_widget
  local has_exclusive_focus = selected_widget ~= nil and not self._using_cursor_navigation

  self:_enable_settings_overlay(has_exclusive_focus)
  self:set_can_exit(not has_exclusive_focus, not has_exclusive_focus)

  return selected_widget
end

DMFOptionsView._change_navigation_column = function (self, column_index)
  local navigation_widgets = self._navigation_widgets
  local num_columns = #navigation_widgets
  local success = false

  if column_index < 1 or num_columns < column_index or self._navigation_column_changed_this_frame then
    return success
  else
    success = true
    self._navigation_column_changed_this_frame = true
  end

  local widgets = navigation_widgets[column_index]

  for i = 1, #widgets do
    local widget = widgets[i]
    local content = widget.content
    local hotspot = content.hotspot or content.button_hotspot

    if hotspot and hotspot.is_selected then
      self:_set_selected_navigation_widget(widget)

      return success
    end
  end

  local widget = focusable_widget_at_scroll_position(widgets, self._navigation_grids[column_index])

  if widget then
    self:_set_selected_navigation_widget(widget)

    return success
  end

  if column_index == CATEGORIES_GRID then
    self:_focus_category_filter()
  else
    self:_focus_header_control("filter")
  end

  return success
end

DMFOptionsView._set_default_navigation_widget = function (self)
  local navigation_widgets = self._navigation_widgets

  for i = 1, #navigation_widgets do
    if self:_change_navigation_column(i) then
      return
    end
  end
end

DMFOptionsView._set_selected_navigation_widget = function (self, widget)
  if widget then
    self:_clear_header_navigation()
    self:_clear_category_filter_navigation()
  end

  local widget_name = widget and widget.name
  local selected_row, selected_column = nil
  local navigation_widgets = self._navigation_widgets

  for column_index = 1, #navigation_widgets do
    local widgets = navigation_widgets[column_index]
    local _, focused_grid_index = self:_set_focused_grid_widget(widgets, widget_name)

    if focused_grid_index then
      self:_set_selected_grid_widget(widgets, widget_name)

      selected_row = focused_grid_index
      selected_column = column_index
    end
  end

  local navigation_grids = self._navigation_grids

  for column_index = 1, #navigation_grids do
    local selected_grid = column_index == selected_column
    local navigation_grid = navigation_grids[column_index]

    navigation_grid:select_grid_index(selected_grid and selected_row or nil, nil, nil, column_index == CATEGORIES_GRID)
  end

  self._selected_navigation_row_index = selected_row
  self._selected_navigation_column_index = selected_column
end

DMFOptionsView._set_focused_grid_widget = function (self, widgets, widget_name)
  local selected_widget, selected_widget_index = nil

  for i = 1, #widgets do
    local widget = widgets[i]
    local is_focused = widget.name == widget_name
    local content = widget.content
    local hotspot = content.hotspot or content.button_hotspot

    if hotspot then
      hotspot.is_focused = is_focused

      if is_focused then
        selected_widget = widget
        selected_widget_index = i
      end
    end
  end

  return selected_widget, selected_widget_index
end

DMFOptionsView._set_selected_grid_widget = function (self, widgets, widget_name)
  local selected_widget, selected_widget_index = nil

  for i = 1, #widgets do
    local widget = widgets[i]
    local is_selected = widget.name == widget_name
    local content = widget.content
    local hotspot = content.hotspot or content.button_hotspot

    if hotspot then
      hotspot.is_selected = is_selected

      if is_selected then
        selected_widget = widget
        selected_widget_index = i
      end
    end
  end

  return selected_widget, selected_widget_index
end

-- Handles navigation to the last selected category widget
DMFOptionsView._on_view_load_complete = function (self, loaded)
  DMFOptionsView.super._on_view_load_complete(self, loaded)

  if _last_selected_category_entry and _last_selected_category_widget then
    self:cb_on_category_pressed(_last_selected_category_widget, _last_selected_category_entry)
  end
end

return DMFOptionsView
