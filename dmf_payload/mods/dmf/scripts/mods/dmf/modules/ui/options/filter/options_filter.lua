local OptionsFilter = {}
local COLOR_FORMAT_PATTERN = "{#[^}]+}"

local function searchable_text(text)
  return Utf8.lower(tostring(text or ""):gsub(COLOR_FORMAT_PATTERN, ""))
end

local function escape_pattern(text)
  return text:gsub("([%(%)%.%%%+%-%*%?%[%]%^%$])", "%%%1")
end

local function search_pattern(filter_text)
  local parts = {}

  for term in string.gmatch(searchable_text(filter_text), "%S+") do
    parts[#parts + 1] = escape_pattern(term)
  end

  return table.concat(parts, ".*")
end

local function is_focusable(data)
  local content = data.widget and data.widget.content

  return content and (content.hotspot or content.button_hotspot)
end

local function add_ancestors(category_data, visible, included, start_index)
  local parent_index = category_data[start_index].parent_index

  while parent_index do
    if included[parent_index] then
      return
    end

    if visible[parent_index] then
      included[parent_index] = true
    end

    parent_index = category_data[parent_index].parent_index
  end
end

local function add_nearest_group_options(category_data, visible, included, group_index)
  local group_depth = category_data[group_index].entry.indentation_level or 0
  local nearest_depth
  local nearest_indices = {}

  for i = group_index + 1, #category_data do
    local data = category_data[i]
    local depth = data.entry.indentation_level or 0

    if depth <= group_depth then
      break
    end

    if visible[i] and is_focusable(data) then
      local relative_depth = depth - group_depth

      if not nearest_depth or relative_depth < nearest_depth then
        nearest_depth = relative_depth
        nearest_indices = { i }
      elseif relative_depth == nearest_depth then
        nearest_indices[#nearest_indices + 1] = i
      end
    end
  end

  for i = 1, #nearest_indices do
    included[nearest_indices[i]] = true
  end
end

local function matches_filter(data, pattern, include_id)
  if string.find(data.search_text, pattern) then
    return true
  end

  return include_id and string.find(data.id_search_text, pattern) ~= nil
end

OptionsFilter.prepare = function (category_data)
  local ancestor_stack = {}

  for i = 1, #category_data do
    local data = category_data[i]
    local depth = data.entry.indentation_level or 0

    while #ancestor_stack > 0 do
      local ancestor_index = ancestor_stack[#ancestor_stack]
      local ancestor_depth = category_data[ancestor_index].entry.indentation_level or 0

      if ancestor_depth < depth then
        break
      end

      ancestor_stack[#ancestor_stack] = nil
    end

    data.search_text = searchable_text(data.entry.display_name)
    data.id_search_text = searchable_text(data.entry.search_id)
    data.parent_index = ancestor_stack[#ancestor_stack]
    ancestor_stack[#ancestor_stack + 1] = i
  end
end

OptionsFilter.filter = function (category_data, filter_text, include_id)
  local pattern = search_pattern(filter_text)
  local visible = {}
  local included = {}

  for i = 1, #category_data do
    visible[i] = not category_data[i].entry.hidden
  end

  if pattern == "" then
    for i = 1, #category_data do
      included[i] = visible[i]
    end
  else
    for i = 1, #category_data do
      local data = category_data[i]
      local entry = data.entry

      if visible[i] and matches_filter(data, pattern, include_id) then
        included[i] = true

        if entry.widget_type == "group_header" then
          add_nearest_group_options(category_data, visible, included, i)
        end
      end
    end

    for i = 1, #category_data do
      if included[i] then
        add_ancestors(category_data, visible, included, i)
      end
    end
  end

  local filtered_data = {}

  for i = 1, #category_data do
    if included[i] then
      filtered_data[#filtered_data + 1] = category_data[i]
    end
  end

  return filtered_data
end

return OptionsFilter
