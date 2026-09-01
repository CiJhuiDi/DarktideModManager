---@class DMFMod
local dmf = get_mod("DMF")

local _declared_packages = {}
local _manual_packages = {}

local ERRORS = {
  REGULAR = {
    package_already_loaded = "[DMF Package Manager] (load_package): package '%s' has already been loaded.",
    package_not_found = "[DMF Package Manager] (load_package): could not find package '%s'.",
    package_already_queued = "[DMF Package Manager] (load_package): package '%s' is already queued for loading.",
    package_not_loaded = "[DMF Package Manager] (unload_package): package '%s' has not been loaded.",
    declared_packages_wrong_type = "[DMF Package Manager] (.mod packages): expected a table, not %s.",
    declared_packages_not_array = "[DMF Package Manager] (.mod packages): expected an array of package names.",
    declared_package_wrong_type = "[DMF Package Manager] (.mod packages): package at index %d must be a non-empty string.",
    declared_package_duplicate = "[DMF Package Manager] (.mod packages): package '%s' is listed more than once.",
    declared_package_not_found = "[DMF Package Manager] (.mod packages): could not find package '%s'.",
  },
  PREFIX = {
    package_loaded_callback = "[DMF Package Manager] '%s' package loaded callback execution",
  },
}

local WARNINGS = {
  force_unloading_package = "[DMF Package Manager] Force-unloading package '%s'. Please make sure to properly " ..
                             "release packages when the mod is unloaded",
  cancelling_package_load = "[DMF Package Manager] Cancelling package load for '%s'. Please make sure to properly " ..
                             "release packages when the mod is unloaded",
}

-- #####################################################################################################################
-- ##### Local functions ###############################################################################################
-- #####################################################################################################################

local function package_records(registry, mod)
  local records = registry[mod]

  if not records then
    records = {}
    registry[mod] = records
  end

  return records
end

local function package_exists(mod, package_name, error_message)
  if Application.can_get_resource("package", package_name) then
    return true
  end

  mod:error(error_message or ERRORS.REGULAR.package_not_found, package_name)

  return false
end

local function package_reference_name(mod)
  return "DMF/" .. mod:get_name()
end

local function run_package_callback(mod, package_name, callback)
  if callback then
    dmf.safe_call_nr(mod, {ERRORS.PREFIX.package_loaded_callback, package_name}, callback, package_name)
  end
end

local function load_async_package(mod, package_name, callback, records)
  local record = {}
  local on_loaded

  if callback then
    on_loaded = function()
      if records[package_name] == record then
        run_package_callback(mod, package_name, callback)
      end
    end
  end

  records[package_name] = record
  record.id = Managers.package:load(package_name, package_reference_name(mod), on_loaded)
end

local function load_sync_package(mod, package_name, callback, records)
  local resource_package = Application.resource_package(package_name)

  ResourcePackage.load(resource_package)
  ResourcePackage.flush(resource_package)

  records[package_name] = {
    resource_package = resource_package,
  }

  run_package_callback(mod, package_name, callback)
end

local function release_package(record)
  if record.id then
    Managers.package:release(record.id)
  else
    ResourcePackage.unload(record.resource_package)
    ResourcePackage.flush(record.resource_package)
    Application.release_resource_package(record.resource_package)
  end
end

local function release_registry_packages(registry, mod, warn)
  local records = registry[mod]

  if not records then
    return
  end

  registry[mod] = nil

  local package_names = table.keys(records)

  for _, package_name in ipairs(package_names) do
    local record = records[package_name]

    records[package_name] = nil

    if warn then
      local is_loaded = record.resource_package or Managers.package:has_loaded_id(record.id)
      local warning = is_loaded and WARNINGS.force_unloading_package or WARNINGS.cancelling_package_load

      mod:warning(warning, package_name)
    end

    release_package(record)
  end
end

local function declared_package_count(mod, packages)
  local count = 0
  local highest_index = 0

  for index in pairs(packages) do
    if type(index) ~= "number" or index < 1 or index % 1 ~= 0 then
      mod:error(ERRORS.REGULAR.declared_packages_not_array)
      return
    end

    count = count + 1
    highest_index = math.max(highest_index, index)
  end

  if count ~= highest_index then
    mod:error(ERRORS.REGULAR.declared_packages_not_array)
    return
  end

  return count
end

-- #####################################################################################################################
-- ##### DMFMod ########################################################################################################
-- #####################################################################################################################

--[[
  Loads a mod package.
  * package_name [string]  : package name. needs to be the full path to the `.package` file without the extension
  * callback     [function]: (optional) callback for when loading is done
  * sync         [boolean] : (optional) load the package synchronously, freezing the game until it is loaded
--]]
function DMFMod:load_package(package_name, callback, sync)
  if dmf.check_wrong_argument_type(self, "load_package", "package_name", package_name, "string") or
     dmf.check_wrong_argument_type(self, "load_package", "callback", callback, "function", "nil") or
     dmf.check_wrong_argument_type(self, "load_package", "sync", sync, "boolean", "nil")
  then
    return
  end

  local records = _manual_packages[self]
  local record = records and records[package_name]

  if record then
    local is_loaded = record.resource_package or Managers.package:has_loaded_id(record.id)
    local error_message = is_loaded and ERRORS.REGULAR.package_already_loaded
                                     or ERRORS.REGULAR.package_already_queued

    self:error(error_message, package_name)
    return
  end

  if not package_exists(self, package_name) then
    return
  end

  records = records or package_records(_manual_packages, self)

  if sync then
    load_sync_package(self, package_name, callback, records)
  else
    load_async_package(self, package_name, callback, records)
  end
end

--[[
  Unloads a package loaded with `load_package`.
  * package_name [string]: package name. needs to be the full path to the `.package` file without the extension
--]]
function DMFMod:unload_package(package_name)
  if dmf.check_wrong_argument_type(self, "unload_package", "package_name", package_name, "string") then
    return
  end

  local records = _manual_packages[self]
  local record = records and records[package_name]

  if not record then
    self:error(ERRORS.REGULAR.package_not_loaded, package_name)
    return
  end

  release_package(record)
  records[package_name] = nil

  if not next(records) then
    _manual_packages[self] = nil
  end
end

--[[
  Returns the status of a package loaded with `load_package`.
  * package_name [string]: package name. needs to be the full path to the `.package` file without the extension
--]]
function DMFMod:package_status(package_name)
  if dmf.check_wrong_argument_type(self, "package_status", "package_name", package_name, "string") then
    return
  end

  local records = _manual_packages[self]
  local record = records and records[package_name]

  if not record then
    return
  end

  if record.resource_package or Managers.package:has_loaded_id(record.id) then
    return "loaded"
  end

  return "loading"
end

-- #####################################################################################################################
-- ##### DMF internal functions and variables ##########################################################################
-- #####################################################################################################################

function dmf.initialize_mod_packages(mod)
  local packages = mod._declared_package_names

  mod._declared_package_names = nil

  if packages == nil then
    return
  end

  if type(packages) ~= "table" then
    mod:error(ERRORS.REGULAR.declared_packages_wrong_type, type(packages))
    return
  end

  local count = declared_package_count(mod, packages)

  if not count or count == 0 then
    return
  end

  local records = package_records(_declared_packages, mod)

  for index = 1, count do
    local package_name = packages[index]

    if type(package_name) ~= "string" or package_name == "" then
      mod:error(ERRORS.REGULAR.declared_package_wrong_type, index)
    elseif records[package_name] then
      mod:error(ERRORS.REGULAR.declared_package_duplicate, package_name)
    elseif package_exists(mod, package_name, ERRORS.REGULAR.declared_package_not_found) then
      load_async_package(mod, package_name, nil, records)
    end
  end

  if not next(records) then
    _declared_packages[mod] = nil
  end
end

function dmf.release_mod_packages(mod)
  release_registry_packages(_manual_packages, mod, false)
  release_registry_packages(_declared_packages, mod, false)
end

function dmf.unload_all_resource_packages()
  local manual_package_mods = table.keys(_manual_packages)

  for _, mod in ipairs(manual_package_mods) do
    release_registry_packages(_manual_packages, mod, true)
  end

  local declared_package_mods = table.keys(_declared_packages)

  for _, mod in ipairs(declared_package_mods) do
    release_registry_packages(_declared_packages, mod, false)
  end
end
