local ColorPickerGamepad = {}

local HSV_SPEED = 0.7
local HUE_SPEED = 240
local ALPHA_SPEED = 170

local function set_item_focus(self, item, focused, active)
  local widget = self._widgets_by_name[item.widget_name]
  local content = widget.content

  if item.kind == "field" then
    local has_focus = focused or content.is_writing

    content.hotspot.is_focused = has_focus
    content.hotspot.is_selected = has_focus
  else
    content.gamepad_focused = focused
    content.gamepad_active = active
  end

  if item.kind == "button" then
    content.hotspot.is_selected = focused
  end
end

local function update_focus(self)
  local focused_id = self._gamepad_focus_id
  local active_id = self._gamepad_active_id
  local items = self._gamepad_navigation_items

  for i = 1, #items do
    local item = items[i]

    set_item_focus(self, item, item.id == focused_id, item.id == active_id)
  end
end

local function move_focus(self, direction)
  local items_by_id = self._gamepad_navigation_items_by_id
  local current_item = items_by_id[self._gamepad_focus_id]
  local navigation = current_item.navigation
  local next_id = navigation and navigation[direction]

  if next_id then
    self._gamepad_focus_id = next_id
  end
end

local function update_active_control(self, dt, input_service)
  local active_id = self._gamepad_active_id

  if input_service:get("confirm_pressed") or input_service:get("back") then
    self._gamepad_active_id = nil

    return
  end

  local controller_axis = input_service:get("navigate_controller")
  local x_axis = controller_axis and controller_axis[1] or 0
  local y_axis = controller_axis and controller_axis[2] or 0

  if x_axis == 0 and y_axis == 0 then
    return
  end

  if active_id == "sv" then
    self:_set_from_hsv(self._hue, self._saturation + x_axis * HSV_SPEED * dt, self._value + y_axis * HSV_SPEED * dt)
  elseif active_id == "hue" then
    self:_set_from_hsv(self._hue - y_axis * HUE_SPEED * dt, self._saturation, self._value)
  elseif active_id == "alpha" then
    self:_set_alpha(self._draft_color[1] + y_axis * ALPHA_SPEED * dt)
  end
end

local function activate_focused_item(self)
  local focused_item = self._gamepad_navigation_items_by_id[self._gamepad_focus_id]
  local kind = focused_item.kind

  if kind == "picker" then
    self:_commit_writing_fields()
    self._gamepad_active_id = focused_item.id

    return false
  elseif kind == "field" then
    return false
  elseif focused_item.id == "back" then
    self:_close()

    return true
  end

  return false
end

ColorPickerGamepad.init = function (picker, navigation_items)
  picker._gamepad_navigation_items = navigation_items
  picker._gamepad_navigation_items_by_id = {}

  for i = 1, #navigation_items do
    local item = navigation_items[i]
    picker._gamepad_navigation_items_by_id[item.id] = item
  end
end

ColorPickerGamepad.clear = function (picker, keep_focus)
  picker._gamepad_active_id = nil

  if not picker._gamepad_focus_id then
    return
  end

  if not keep_focus then
    picker._gamepad_focus_id = nil
  end

  for i = 1, #picker._gamepad_navigation_items do
    set_item_focus(picker, picker._gamepad_navigation_items[i], false, false)
  end
end

ColorPickerGamepad.on_navigation_input_changed = function (picker, using_cursor_navigation)
  if using_cursor_navigation then
    picker._gamepad_active_id = nil
    ColorPickerGamepad.clear(picker, true)
  else
    local widgets_by_name = picker._widgets_by_name
    widgets_by_name.sv.content.drag_active = nil
    widgets_by_name.hue.content.drag_active = nil

    if picker._has_alpha then
      widgets_by_name.alpha.content.drag_active = nil
    end

    if picker._gamepad_focus_id then
      update_focus(picker)
    end
  end
end

ColorPickerGamepad.update = function (picker, dt, input_service)
  if not picker._gamepad_focus_id then
    picker._gamepad_focus_id = "sv"
  end

  local focused_item = picker._gamepad_navigation_items_by_id[picker._gamepad_focus_id]

  local focused_content = picker._widgets_by_name[focused_item.widget_name].content

  if focused_item.kind == "field" and focused_content.is_writing then
    if input_service:get("back") then
      picker:_stop_field_writing(focused_item.id)
    end

    update_focus(picker)

    return false
  elseif picker._gamepad_active_id then
    update_active_control(picker, dt, input_service)
  elseif input_service:get("back") then
    picker:_close()

    return true
  elseif input_service:get("confirm_pressed") then
    if activate_focused_item(picker) then
      return true
    end
  elseif input_service:get("navigate_left_continuous") then
    move_focus(picker, "left")
  elseif input_service:get("navigate_right_continuous") then
    move_focus(picker, "right")
  elseif input_service:get("navigate_up_continuous") then
    move_focus(picker, "up")
  elseif input_service:get("navigate_down_continuous") then
    move_focus(picker, "down")
  end

  update_focus(picker)

  return false
end

return ColorPickerGamepad
