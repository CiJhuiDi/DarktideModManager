---@class DMFMod
local dmf = get_mod("DMF")

local OptionsDisplayUtils = dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/options_display_utils")

local OptionsUtilities = require("scripts/utilities/ui/options")

local _type_template_map = {}

local _devices = {
  "keyboard",
  "mouse",
}

local _cancel_keys = {
  "keyboard_esc"
}

local _reserved_keys = {}

local ERRORS = {
  REGULAR = {
    invalid_widget_type = "[DMF Mod Options] (%s): \"%s\" is not a valid widget type " ..
                                              "in this version of Darktide Mod Framework.",
  },
}

-- ####################################################################################################################
-- ##### Local functions ##############################################################################################
-- ####################################################################################################################

-- ##########################
-- ###### Group #############
-- ##########################

-- Create group template
local create_group_template = function(self, params)
  local template = {
    display_name = params.title,
    indentation_level = params.depth,
    widget_type = "group_header",
    after = params.parent_index
  }
  return template
end
_type_template_map["group"] = create_group_template

-- ##########################
-- ###### Button ############
-- ##########################

local function call_button_function(mod, function_name)
  local func = mod[function_name]

  if type(func) == "function" then
    dmf.safe_call_nr(mod, {"[Button] function_call 'mod.%s'", function_name}, func)
  else
    mod:error("[Button] function_call 'mod.%s': function was not found.", function_name)
  end
end


local create_button_template = function (self, params)
  local mod = get_mod(params.mod_name)
  local function_name = params.function_name
  local template = {
    after = params.parent_index,
    button_hold_duration = params.button_hold_duration,
    button_text = params.button_text,
    button_trigger = params.button_trigger,
    category = params.category,
    display_name = params.title,
    indentation_level = params.depth,
    mod_name = params.mod_name,
    tooltip_text = params.tooltip,
    widget_type = "button",
    pressed_function = function ()
      call_button_function(mod, function_name)
    end,
  }

  return template
end
_type_template_map["button"] = create_button_template

-- ###########################
-- ###### Percent Slider #####
-- ###########################

-- Create percentage slider template
local create_percent_slider_template = function (self, params)

  params.on_value_changed_function = function(new_value)
    get_mod(params.mod_name):set(params.setting_id, new_value, true)

    return true
  end
  params.value_get_function = function()
    return get_mod(params.mod_name):get(params.setting_id)
  end

  params.display_name = params.title
  params.apply_on_drag = true
  params.default_value = params.default_value
  params.normalized_step_size = 1 / 100

  local template = OptionsUtilities.create_percent_slider_template(params)

  template.after = params.parent_index
  template.category = params.category
  template.indentation_level = params.depth
  template.tooltip_text = params.tooltip

  return template
end
_type_template_map["percent_slider"] = create_percent_slider_template


-- ###########################
-- ###### Value Slider #######
-- ###########################

-- Create value slider template
local create_value_slider_template = function (self, params)
  local number_format = string.format("%%.%sf", params.decimals_number)

  params.on_value_changed_function = function(new_value)
    get_mod(params.mod_name):set(params.setting_id, new_value, true)

    return true
  end
  params.value_get_function = function()
    return get_mod(params.mod_name):get(params.setting_id)
  end

  params.display_name = params.title
  params.apply_on_drag = true
  params.default_value = params.default_value
  params.max_value = params.range[2]
  params.min_value = params.range[1]
  params.num_decimals = params.decimals_number
  params.step_size_value = params.step_size_value or math.pow(10, params.decimals_number * -1)
  params.explode_function = function (normalized_value)
    local value_range = params.max_value - params.min_value
    local value = params.min_value + math.clamp(normalized_value, 0, 1) * value_range
    local step_count = math.round((value - params.min_value) / params.step_size_value)

    return math.clamp(params.min_value + step_count * params.step_size_value, params.min_value, params.max_value)
  end
  params.type = "value_slider"
  params.format_value_function = params.format_value_function or function (value)
    return string.format(number_format, value)
  end

  local template = OptionsUtilities.create_value_slider_template(params)

  template.after = params.parent_index
  template.category = params.category
  template.indentation_level = params.depth
  template.num_decimals = params.num_decimals
  template.tooltip_text = params.tooltip
  template.unit_text = params.unit_text

  return template
end
_type_template_map["value_slider"] = create_value_slider_template
_type_template_map["numeric"] = create_value_slider_template


-- ######################
-- ######## Color #######
-- ######################

local create_color_template = function (self, params)
  local template = {
    after = params.parent_index,
    category = params.category,
    default_value = params.default_value,
    display_name = params.title,
    has_alpha = params.has_alpha,
    indentation_level = params.depth,
    mod_name = params.mod_name,
    require_restart = params.require_restart,
    setting_id = params.setting_id,
    tooltip_text = params.tooltip,
    widget_type = "color",
  }

  template.on_activated = function (new_value)
    get_mod(params.mod_name):set(params.setting_id, new_value, true)

    return true
  end

  template.get_function = function ()
    return get_mod(params.mod_name):get(params.setting_id)
  end

  return template
end
_type_template_map["color"] = create_color_template


-- ######################
-- ###### Checkbox ######
-- ######################

-- Create checkbox template
local create_checkbox_template = function (self, params)
  local template = {
    after = params.parent_index,
    category = params.category,
    default_value = params.default_value,
    display_name = params.title,
    indentation_level = params.depth,
    options_tab_focus_self = true,
    require_restart = params.require_restart,
    tooltip_text = params.tooltip,
    value_type = "boolean",
  }
  template.on_activated = function(new_value)
    get_mod(params.mod_name):set(params.setting_id, new_value, true)

    return true
  end
  template.get_function = function()
    return get_mod(params.mod_name):get(params.setting_id)
  end

  return template
end
_type_template_map["checkbox"] = create_checkbox_template


-- ########################
-- ###### Mod Toggle ######
-- ########################

-- Create mod toggle template
local create_mod_toggle_template = function (self, params)
  local tooltip_metadata = OptionsDisplayUtils.metadata_text(params.version, params.author)
  local template = {
    after = params.after,
    category = params.category,
    default_value = true,
    disabled = params.disabled,
    display_name = params.readable_mod_name or params.mod_name,
    indentation_level = 0,
    require_restart = params.require_restart,
    search_id = params.mod_name,
    tooltip_identifier = params.mod_name ~= "" and params.mod_name or nil,
    tooltip_metadata = tooltip_metadata ~= "" and tooltip_metadata or nil,
    tooltip_text = params.description ~= "" and params.description or nil,
    value_type = "boolean",
  }

  template.on_activated = function(new_value)
    dmf.mod_state_changed(params.mod_name, new_value)

    return true
  end
  template.get_function = function()
    return get_mod(params.mod_name):is_enabled()
  end

  return template
end
_type_template_map["mod_toggle"] = create_mod_toggle_template


-- ######################
-- ###### Dropdown ######
-- ######################

-- Create dropdown template
local create_dropdown_template = function (self, params)

  for i = 1, #params.options do
    params.options[i].id = i - 1
    params.options[i].display_name = params.options[i].text
  end

  local template = {
    after = params.parent_index,
    category = params.category,
    default_value = params.default_value,
    display_name = params.title,
    indentation_level = params.depth,
    options = params.options,
    options_tab_focus_self = true,
    tooltip_text = params.tooltip,
    require_restart = params.require_restart,
    widget_type = "dropdown",
  }
  template.on_activated = function(new_value)
    get_mod(params.mod_name):set(params.setting_id, new_value, true)

    return true
  end
  template.get_function = function()
    return get_mod(params.mod_name):get(params.setting_id)
  end

  return template
end
_type_template_map["dropdown"] = create_dropdown_template


-- ###########################
-- ######### Keybind #########
-- ###########################

local set_keybind = function (self, keybind_data, keywatch_result)
  keybind_data.keys = keywatch_result

  local mod = get_mod(keybind_data.mod_name)
  dmf.add_mod_keybind(
    mod,
    keybind_data.setting_id,
    {
      global          = keybind_data.keybind_global,
      trigger         = keybind_data.keybind_trigger,
      type            = keybind_data.keybind_type,
      main            = keywatch_result.main,
      enablers        = keywatch_result.enablers,
      disablers       = keywatch_result.disablers,
      function_name   = keybind_data.function_name,
      view_name       = keybind_data.view_name,
    }
  )
  mod:set(keybind_data.setting_id, dmf.keywatch_result_to_local_keys(keywatch_result), true)
end


-- Create keybind template
local create_keybind_template = function (self, params)
  local template = {
    widget_type = "keybind",
    service_type = "Ingame",
    tooltip_text = params.tooltip,
    display_name = params.title,
    group_name = params.category,
    category = params.category,
    after = params.parent_index,
    devices = _devices,
    sort_order = params.sort_order,
    cancel_keys = _cancel_keys,
    reserved_keys = _reserved_keys,
    indentation_level = params.depth,
    mod_name = params.mod_name,
    setting_id = params.setting_id,
    keys = dmf.local_keys_to_keywatch_result(params.keys),
    default_value = dmf.local_keys_to_keywatch_result(params.default_value) or {},

    on_activated = function (new_value, old_value)
      -- Unbind the keybind if the new value is empty
      if not (new_value and new_value.main) then
        set_keybind(self, params, {})
        return true
      end

      -- Unbind the keybind if the new value matches a cancel key
      for i = 1, #_cancel_keys do
        local cancel_key = _cancel_keys[i]
        if cancel_key == new_value.main then
          set_keybind(self, params, {})
          return true
        end
      end

      -- Don't modify the keybind if the new value is a reserved key
      for i = 1, #_reserved_keys do
        local reserved_key = _reserved_keys[i]
        if reserved_key == new_value.main then
          return false
        end
      end

      -- Get the keys of the new value
      local keys = dmf.keywatch_result_to_local_keys(new_value)

      if keys and #keys > 0 then
        set_keybind(self, params, new_value)
        return true
      end

      return false
    end,

    get_function = function (template)
      local saved_keys = get_mod(template.mod_name):get(template.setting_id)
      local keywatch_result = dmf.local_keys_to_keywatch_result(saved_keys)

      return keywatch_result
    end,
  }

  return template
end
_type_template_map["keybind"] = create_keybind_template

-- ##############################
-- ############ Text ############
-- ##############################

local create_text_template = function (self, params)
  local template = {
    after = params.parent_index,
    category = params.category,
    default_value = params.default_value,
    display_name = params.title,
    indentation_level = params.depth,
    max_length = params.max_length,
    placeholder_text = params.placeholder_text,
    require_restart = params.require_restart,
    show_length_limit = params.show_length_limit,
    tooltip_text = params.tooltip,
    validate = params.validate,
    widget_type = "text",
    mod_name = params.mod_name,
    setting_id = params.setting_id
  }

  template.on_activated = function(new_value)
    get_mod(params.mod_name):set(params.setting_id, new_value, true)

    return true
  end

  template.get_function = function()
    return get_mod(params.mod_name):get(params.setting_id)
  end

  return template
end
_type_template_map["text"] = create_text_template

-- ##############################
-- ######### Text Input #########
-- ##############################

local create_text_input_template = function (self, params)
  local template = {
    after = params.parent_index,
    category = params.category,
    default_value = params.default_value or "",
    display_name = params.title,
    indentation_level = params.depth,
    tooltip_text = params.tooltip,
    widget_type = "text_input",
    mod_name = params.mod_name,
    setting_id = params.setting_id,
    function_name = params.function_name
  }

  template.on_activated = function(new_value)
    local mod = get_mod(params.mod_name)

    mod:set(params.setting_id, new_value, true)

    if template.function_name and mod[template.function_name] then
      dmf.safe_call_nr(mod, { "[Text Input] function_call", template.function_name }, mod[template.function_name], true)
    end

    return true
  end

  template.get_function = function()
    return get_mod(params.mod_name):get(params.setting_id)
  end

  return template
end
_type_template_map["text_input"] = create_text_input_template


-- ###########################
-- ###### Miscellaneous ######
-- ###########################

-- Get the template creation function associated with a given widget data type
local function widget_data_to_template(self, data)
  if data and data.type and type(data.type) == "string" and _type_template_map[data.type] then
    local template = _type_template_map[data.type](self, data)

    template.search_id = template.search_id or data.setting_id
    template.setting_id = data.setting_id

    if data.has_sub_widgets and (data.type == "checkbox" or data.controls_sub_widgets) then
      template.controls_sub_widgets = true
      template.mod_name = data.mod_name
    end

    return template
  else
    dmf:dump(data, "widget", 1)
    dmf:error(ERRORS.REGULAR.invalid_widget_type, tostring(data.mod_name), tostring(data.type))
  end
end


-- Add a category for toggling mods
local function create_toggle_category(self, categories)
  local category = {
    can_be_reset            = false,
    description             = dmf:localize("toggle_mods_description"),
    display_name            = dmf:localize("toggle_mods"),
    custom                  = true,
    is_toggle_mods_category = true,
  }
  categories[#categories + 1] = category
  return category
end


local function is_favorited_mod(mod_name)
  local favorited_mods = dmf:get("options_menu_favorite_mods")

  for i = 1, #favorited_mods do
    if favorited_mods[i] == mod_name then
      return true
    end
  end

  return false
end


--  Add a mod category to the options view categories
local function create_mod_category(self, categories, widget_data)
  local category = {
    can_be_reset = widget_data.can_be_reset or true,
    description  = widget_data.description,
    display_name = widget_data.readable_mod_name or widget_data.mod_name or "",
    version      = widget_data.version,
    author       = widget_data.author,
    custom       = true,
    is_favorited = is_favorited_mod(widget_data.mod_name),
    is_togglable = widget_data.is_togglable,
    mod_name     = widget_data.mod_name,
  }
  categories[#categories + 1] = category
  return category
end


local function has_focusable_descendant(widgets, widget_index)
  local depth = widgets[widget_index].depth

  for i = widget_index + 1, #widgets do
    local widget = widgets[i]

    if widget.depth <= depth then
      break
    end

    if widget.type ~= "group" then
      return true
    end
  end

  return false
end


local function dropdown_shown_widgets(widget)
  local value = get_mod(widget.mod_name):get(widget.setting_id)

  for i = 1, #widget.options do
    local option = widget.options[i]

    if option.value == value then
      return option.show_widgets
    end
  end
end


local function update_widget_set_visibility(widget_set)
  local widgets = widget_set.widgets
  local templates = widget_set.templates
  local visible = {
    [1] = true,
  }
  local dropdown_children = {}
  local changed = false

  for i = 2, #widgets do
    local widget = widgets[i]
    local parent = widgets[widget.parent_index]
    local is_visible = visible[widget.parent_index] ~= false

    if is_visible and parent.type == "checkbox" then
      is_visible = get_mod(parent.mod_name):get(parent.setting_id) == true
    elseif is_visible and parent.type == "dropdown" and parent.controls_sub_widgets then
      local shown_widgets = dropdown_children[parent.index]

      if shown_widgets == nil then
        shown_widgets = dropdown_shown_widgets(parent) or false
        dropdown_children[parent.index] = shown_widgets
      end

      is_visible = shown_widgets and shown_widgets[widget.index] or false
    end

    visible[widget.index] = is_visible

    local template = templates[widget.index]

    if template then
      local hidden = not is_visible

      if template.hidden ~= hidden then
        template.hidden = hidden
        changed = true
      end
    end
  end

  return changed
end

-- Insert a new item into a table before any items that pass the item_tester function
local function insert_before(tbl, item_tester, new_item)
  local copy = {}
  for _, item in ipairs(tbl) do
    if item_tester(item) then
      table.insert(copy, new_item)
    end
    table.insert(copy, item)
  end
  return copy
end


-- ####################################################################################################################
-- ##### Hooks ########################################################################################################
-- ####################################################################################################################

-- Add Mods Options title to global localization table
-- so that the SystemView options menu can localize it
dmf:add_global_localize_strings({
  -- TODO: copied from dmf/localization/dmf.lua, figure out a better way
  mods_options = {
    en = "Mod Options",
    es = "Configuración de mods",
    ru = "Настройки модов",
    ["zh-cn"] = "模组选项",
    ja = "Modオプション",
  }
})

local dmf_option_definition = {
  text = "mods_options",
  type = "button",
  icon = "content/ui/materials/icons/system/escape/settings",
  trigger_function = function()
    local context = {
      can_exit = true,
    }
    local view_name = "dmf_options_view"
    Managers.ui:open_view(view_name, nil, nil, nil, nil, context)
  end,
}

local function is_options_button(item)
  return item.text == "loc_options_view_display_name"
end

-- Inject DMF Options button into the Esc menu
dmf:hook_require("scripts/ui/views/system_view/system_view_content_list", function(instance)
  -- Don't re-inject if it's already there
  if table.find_by_key(instance.default, "text", dmf_option_definition.text) then
    return
  end

  instance.default = insert_before(instance.default, is_options_button, dmf_option_definition)
  instance.StateMainMenu = insert_before(instance.StateMainMenu, is_options_button, dmf_option_definition)
end)

-- ####################################################################################################################
-- ##### DMF internal functions and variables #########################################################################
-- ####################################################################################################################

dmf.update_mod_options_visibility = function (self, options_templates, mod_name)
  local widget_sets = options_templates.dynamic_widget_sets

  if mod_name then
    local widget_set = widget_sets[mod_name]

    return widget_set and update_widget_set_visibility(widget_set) or false
  end

  local changed = false

  for _, widget_set in pairs(widget_sets) do
    changed = update_widget_set_visibility(widget_set) or changed
  end

  return changed
end


-- Add mod settings to options view
dmf.create_mod_options_settings = function (self, options_templates)
  local categories = options_templates.categories
  local settings = options_templates.settings
  local dynamic_widget_sets = {}

  options_templates.dynamic_widget_sets = dynamic_widget_sets

  -- Create the toggle category
  local toggle_category = create_toggle_category(self, categories)

  -- Create a toggle for each mod; non-toggleable mods' toggles are disabled
  for _, mod_data in ipairs(dmf.options_widgets_data) do
    local toggle_widget_data = {
      mod_name = mod_data[1].mod_name,
      readable_mod_name = mod_data[1].readable_mod_name or mod_data[1].title,
      description = mod_data[1].description,
      version = mod_data[1].version,
      author = mod_data[1].author,
      disabled = not mod_data[1].is_togglable,
      category = toggle_category.display_name,
      after = #settings,
      type = "mod_toggle"
    }

    local toggle_template = widget_data_to_template(self, toggle_widget_data)
    if toggle_template then
      toggle_template.custom = true
      toggle_template.category = toggle_category.display_name
      settings[#settings + 1] = toggle_template
    end
  end

  -- Create a category for every mod that has additional settings
  for _, mod_data in ipairs(dmf.options_widgets_data) do
    if #mod_data > 1 then
      local category = create_mod_category(self, categories, mod_data[1])
      local templates = {}
      local mod_name = mod_data[1].mod_name

      dynamic_widget_sets[mod_name] = {
        templates = templates,
        widgets = mod_data,
      }

      -- Populate the category with options taken from the remaining options data
      for i = 2, #mod_data do
        local widget_data = mod_data[i]

        local template = widget_data_to_template(self, widget_data)
        if template then
          template.custom = true
          template.category = category.display_name
          template.is_options_tab_candidate = widget_data.depth == 0
            and widget_data.has_sub_widgets
            and has_focusable_descendant(mod_data, i)

          settings[#settings + 1] = template
          templates[widget_data.index] = template
        end
      end
    end
  end

  return options_templates
end


dmf.initialize_dmf_options_view = function ()
  dmf:add_require_path("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view")
  dmf:add_require_path("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view_definitions")
  dmf:add_require_path("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view_settings")
  dmf:add_require_path("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view_content_blueprints")

  dmf:register_view({
    view_name = "dmf_options_view",
    view_settings = {
      init_view_function = function (ingame_ui_context)
        return true
      end,
      class = "DMFOptionsView",
      disable_game_world = false,
      display_name = "loc_options_view_display_name",
      game_world_blur = 1.1,
      load_always = true,
      load_in_hub = true,
      package = "packages/ui/views/options_view/options_view",
      path = "dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view",
      state_bound = true,
      enter_sound_events = {
        "wwise/events/ui/play_ui_enter_short"
      },
      exit_sound_events = {
        "wwise/events/ui/play_ui_back_short"
      },
      wwise_states = {
        options = "ingame_menu"
      }
    },
    view_transitions = {},
    view_options = {
      close_all = false,
      close_previous = false,
      close_transition_time = nil,
      transition_time = nil
    }
  })

  dmf:io_dofile("dmf/scripts/mods/dmf/modules/ui/options/dmf_options_view")
end

-- ####################################################################################################################
-- ##### Script #######################################################################################################
-- ####################################################################################################################
