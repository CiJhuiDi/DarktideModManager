-- Global backup of original print() method
local print = __print

local _io = Mods.lua.io
local _language_id = Application.user_setting("language_id")

-- #####################################################################################################################
-- ##### Local functions ###############################################################################################
-- #####################################################################################################################

local function set_internal_data(mod, key, value)
  getmetatable(mod._data).__index[key] = value
end

local function is_json_object(value)
  return type(value) == "table" and (table.is_empty(value) or not table.is_array(value))
end

local function merge_metadata_object(destination, source)
  for key, source_value in pairs(source) do
    local destination_value = destination[key]
    local source_is_object = type(source_value) == "table" and not table.is_array(source_value)
    local destination_is_object = type(destination_value) == "table" and not table.is_array(destination_value)

    if source_is_object and destination_is_object then
      merge_metadata_object(destination_value, source_value)
    else
      destination[key] = type(source_value) == "table" and table.clone(source_value) or source_value
    end
  end
end

local function load_mod_metadata(load_order_name)
  local file_path = string.format("./../mods/%s/info.json", load_order_name)
  local file = _io.open(file_path, "r")

  if not file then
    return {}
  end

  local contents = file:read("*all")
  file:close()

  local success, metadata = pcall(cjson.decode, contents)

  if not success then
    print(string.format("[DMF] Could not parse '%s': %s", file_path, tostring(metadata)))
    return {}
  end

  if not is_json_object(metadata) then
    print(string.format("[DMF] Could not read '%s': root value must be an object", file_path))
    return {}
  end

  local localization = metadata.localization
  local result = table.clone(metadata)

  result.localization = nil

  if localization == nil then
    return result
  end

  if not is_json_object(localization) then
    print(string.format("[DMF] Could not localize '%s': 'localization' must be an object", file_path))
    return result
  end

  local localized_metadata = localization[_language_id]

  if localized_metadata == nil then
    return result
  end

  if not is_json_object(localized_metadata) then
    print(string.format("[DMF] Could not localize '%s': language '%s' must contain an object", file_path, _language_id))
    return result
  end

  localized_metadata = table.clone(localized_metadata)
  localized_metadata.localization = nil

  merge_metadata_object(result, localized_metadata)

  return result
end

-- #####################################################################################################################
-- ##### DMFMod (not API) ##############################################################################################
-- #####################################################################################################################

-- Defining DMFMod class.
---@class DMFMod
---@field new fun(self: DMFMod, mod_name: string): DMFMod
DMFMod = class("DMFMod")

-- Creating mod data table when object of DMFMod class is created.
function DMFMod:init(mod_name)
  if mod_name == "DMF" then
    self.set_internal_data = set_internal_data
  end

  self._data = setmetatable({}, {
    __index = {},
    __newindex = function(t_, k)
      self:warning("Attempt to change internal mod data value (\"%s\"). Changing internal mod data is forbidden.", k)
    end
  })
  set_internal_data(self, "name",          mod_name)
  set_internal_data(self, "readable_name", mod_name)
  set_internal_data(self, "is_enabled",    true)
  set_internal_data(self, "is_togglable",  false)
  set_internal_data(self, "is_mutator",    false)

  local vanilla_mod_data = Managers.mod._mods[Managers.mod._mod_load_index]
  local mod_file_data = vanilla_mod_data.data

  self._metadata = load_mod_metadata(vanilla_mod_data.name)

  local version = self:get_metadata("version")
  local author = self:get_metadata("author")

  set_internal_data(self, "load_order_id",   vanilla_mod_data.id)
  set_internal_data(self, "load_order_name", vanilla_mod_data.name)
  set_internal_data(self, "workshop_id",     vanilla_mod_data.id)
  set_internal_data(self, "workshop_name",   vanilla_mod_data.name)
  set_internal_data(self, "mod_handle",      vanilla_mod_data.handle)
  self._declared_package_names = mod_file_data.packages

  local log_properties = {
    string.format("load_order_name: '%s'", vanilla_mod_data.name),
    string.format("load_order_id: %s", vanilla_mod_data.id),
  }

  if version ~= nil and tostring(version) ~= "" then
    log_properties[#log_properties + 1] = string.format("version: '%s'", tostring(version))
  end
  if author ~= nil and tostring(author) ~= "" then
    log_properties[#log_properties + 1] = string.format("author: '%s'", tostring(author))
  end

  print(string.format("Init DMF mod '%s' [%s]", mod_name, table.concat(log_properties, ", ")))
end

-- #####################################################################################################################
-- ##### DMFMod ########################################################################################################
-- #####################################################################################################################

--[[
  Universal function for retrieving any internal mod data. Returned table values shouldn't be modified, because it can
  lead to unexpected DMF behaviour.
  * key [string]: data entry name

  Possible entry names:
    - name            (system mod name)
    - readable_name   (readable mod name)
    - load_order_id   (mod load order entry id)
    - load_order_name (mod load order entry name)
    - description     (mod description)
    - is_togglable    (if the mod can be disabled/enabled)
    - is_enabled      (if the mod is curently enabled)
--]]
function DMFMod:get_internal_data(key)
  return self._data[key]
end


--[[
  Retrieves a localized metadata entry from the optional info.json file. Table values are copied before being returned.
  * key [string]: metadata entry name
--]]
function DMFMod:get_metadata(key)
  local value = self._metadata[key]

  if type(value) == "table" then
    return table.clone(value)
  end

  return value
end


--[[
  Predefined functions for retrieving specific internal mod data.
--]]
function DMFMod:get_name()
  return self._data.name
end
function DMFMod:get_readable_name()
  return self._data.readable_name
end
function DMFMod:get_description()
  return self._data.description
end
function DMFMod:is_enabled()
  return self._data.is_enabled
end
