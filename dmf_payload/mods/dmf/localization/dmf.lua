return {
  mods_options = {
    en = "Mod Options",
    ["zh-cn"] = "模组选项",
    es = "Configuración de mods",
    ru = "Настройки модов",
    ja = "Modオプション",
  },
  open_dmf_options = {
    en = "Open Options Menu",
    ["zh-cn"] = "打开选项菜单",
    es = "Abrir el menu de configuración",
    ru = "Открыть меню настроек",
    ja = "オプションメニューを開く",
  },
  open_dmf_options_description = {
    en = "Keybind for opening and closing mods options menu.",
    ["zh-cn"] = "打开或关闭模组选项菜单的按键绑定。",
    es = "Atajo para abrir/cerrar el menu de configuración de mods.",
    ru = "Клавиша/сочетание клавиш для открытия и закрытия меню настроек модов.",
    ja = "オプションメニューを開閉するキーバインド",
  },
  dmf_options_scrolling_speed = {
    en = "Options Menu Scrolling Speed",
    ["zh-cn"] = "选项菜单滚动速度",
    es = "Velocidad de desplazamiento en el menu",
    ru = "Скорость прокрутки меню",
    ja = "オプションメニューのスクロール速度",
  },
  dmf_first_run_notification = {
    en = "Welcome to the Darktide Mod Framework. Mod options have been added to the Options Menu.",
    ["zh-cn"] = "欢迎使用 Darktide Mod Framework。模组选项已添加到选项菜单中。",
    es = "Bienvenidos a el Mod Framework de Darktide. Hemos agregado las opciones de Mod a el menu de opciones.",
    de = "Willkommen beim Darktide Mod Framework. Ein Button für Mod-Optionen wurde dem Hauptmenu hinzugefügt.",
    ru = "Добро пожаловать в Darktide Mod Framework. Параметры мода были добавлены в меню параметров.",
    ja = "Darktide Mod Frameworkのご利用ありがとうございます。Modオプションがオプションメニューに追加されました。",
  },
  percent = {
    en = "%%",
  },
    ["zh-cn"] = "%%",
  toggle_mods = {
    en = "Toggle Mods",
    ["zh-cn"] = "开关模组",
    ru = "Включение/выключение модов",
    ja = "Modのオン/オフ",
  },
  toggle_mods_description = {
    en = "Enable or disable your mods.",
    ["zh-cn"] = "启用或禁用你安装的模组。",
    ru = "Включите или отключите ваши моды.",
    ja = "Modを有効化/無効化します。",
  },
  ui_scaling = {
    en = "UI Scaling for FHD+ Resolutions",
    ["zh-cn"] = "FHD+ 分辨率下的 UI 缩放",
    es = "Reescalado de la interfaz para resoluciones Full HD+",
    ru = "Нормализация масштаба интерфейса для FHD+ разрешений",
    ja = "解像度FHD以上でのUIスケーリング",
  },
  ui_scaling_description = {
    en = "Automatically scale UI when resolution exceeds 1080p.",
    ["zh-cn"] = "当分辨率超过 1080p 时自动缩放 UI。",
    es = "Redimensionar automáticamente la interfaz cuando la resolución exceda 1080p.",
    ru = "Нормализует масштаб элементов интерфейса, если разрешений экрана превышает 1080p.",
    ja = "1080pを超える解像度でUIの大きさを自動調節します。",
  },
  developer_mode = {
    en = "Developer Mode",
    ["zh-cn"] = "开发者模式",
    es = "Modo de desarrollo",
    ru = "Режим разработчика",
    ja = "開発者モード",
  },
  developer_mode_description = {
    en = "Allows you to reload DMF and mods (CTRL+SHIFT+R), gives you access to some debug features.",
    ["zh-cn"] = "允许重新加载 DMF 和模组（CTRL+SHIFT+R），并解锁一些调试功能。",
    es = "Permite recargar los mods (CTRL+SHIFT+R) y configurar herramientas de depuración.",
    ru = "Позволяет перезагружать DMF и моды (CTRL+SHIFT+R), даёт доступ к инструментам отладки.",
    ja = "DMFとModのリロード (CTRL+SHIFT+R) や、いくつかのデバッグ機能へのアクセスを可能にします。",
  },
  show_developer_console = {
    en = "Show Developer Console",
    ["zh-cn"] = "显示开发者控制台",
    es = "Mostrar el registro (log) a tiempo real",
    ru = "Консоль разработчика",
    ja = "開発者コンソールの表示",
  },
  show_developer_console_description = {
    en = "Opens up the new window showing game log in real time.",
    ["zh-cn"] = "打开一个新窗口，实时显示游戏日志。",
    es = "Abre una ventana que muestra el registro (log) del juego en tiempo real.",
    ru = "Открывает новое окно, в которое в реальном времени выводится игровой лог.",
    ja = "ゲームのログをリアルタイムで表示する新たなウィンドウを開きます。",
  },
  toggle_developer_console = {
    en = "Toggle Developer Console",
    ["zh-cn"] = "开关开发者控制台",
    es = "Abrir el registro (log) a tiempo real",
    ru = "Открыть/закрыть консоль разработчика",
    ja = "開発者コンソールの表示/非表示",
  },
  show_network_debug_info = {
    en = "Log Network Calls",
    ["zh-cn"] = "记录网络调用日志",
    es = "Depurar las llamadas de red",
    ru = "Логирование сетевых вызовов",
    ja = "ネットワーク呼び出しの記録",
  },
  show_network_debug_info_description = {
    en = "Log all the DMF network calls and all the data transfered with them.\n\n" ..
         "The method 'info' is used for the logging.",
    ["zh-cn"] = "记录所有 DMF 网络调用及随之传输的数据。\n" ..
        "\n" ..
        "日志使用「info」级别记录。",
    es = "Escribe en el registro todas las llamadas de red (RPCs) que se ejecuten a través de DMF.\n\n" ..
         "Esta información se registra en el nivel 'info'.",
    ru = "Логирование всех сетевых вызовов DMF и передаваемых с ними данных.\n\n" ..
         "Для логирования используется метод 'info'.",
    ja = "すべてのDMFのネットワーク呼び出しと通信データをログに記録します。\n\n" ..
         "記録には 'info' メソッドが使用されます。",
  },
  log_ui_renderers_info = {
    en = "Log UI Renderers Creation Info",
    ["zh-cn"] = "记录 UI 渲染器创建信息",
    es = "Depurar la renderización de la interfaz de usuario",
    ru = "Логирование информации при создании UI Renderer",
    ja = "UIレンダラー生成情報の記録",
  },
  log_ui_renderers_info_description = {
    en = "Log the UI Renderer's creator name and all the materials passed as the arguments.\n\n" ..
         "The method 'info' is used for the logging.",
    ["zh-cn"] = "记录 UI 渲染器的创建者名称，以及作为参数传入的所有材质。\n" ..
        "\n" ..
        "日志使用「info」级别记录。",
    es = "Escribe en el registro cada vez que se inicialize un renderizador de la interfaz.\n\n" ..
         "Esta información se registra en el nivel 'info'.",
    ru = "Логирование имени создателя UI Renderer'а и всех материалов, переданных в качестве аргументов.\n\n" ..
         "Для логирования используется метод 'info'.",
    ja = "UIレンダラー生成元の名称と、引数として渡されたすべてのマテリアルをログに記録します。\n\n" ..
         "記録には 'info' メソッドが使用されます。",
  },
  logging_mode = {
    en = "Logging Settings",
    ["zh-cn"] = "日志设置",
    es = "Opciones de logging",
    ru = "Настройки логирования",
    ja = "ログの設定",
  },
  settings_default = {
    en = "Default",
    ["zh-cn"] = "默认",
    es = "Valor por defecto",
    ru = "Стандартные",
    ja = "デフォルト",
  },
  settings_custom = {
    en = "Custom",
    ["zh-cn"] = "自定义",
    es = "Personalizado",
    ru = "Пользовательские",
    ja = "カスタム",
  },
  output_mode_notification = {
    en = "'Notification' Output",
    ["zh-cn"] = "'Notification' 通知输出",
    ru = "Вывод 'Notification'",
    ja = "'Notification' の出力",
  },
  output_mode_echo = {
    en = "'Echo' Output",
    ["zh-cn"] = "'Echo' 回显输出",
    es = "Mensajes de 'Echo'",
    ru = "Вывод 'Echo'",
    ja = "'Echo' の出力",
  },
  output_mode_error = {
    en = "'Error' Output",
    ["zh-cn"] = "'Error' 错误输出",
    es = "Mensajes de 'Error'",
    ru = "Вывод 'Error'",
    ja = "'Error' の出力",
  },
  output_mode_warning = {
    en = "'Warning' Output",
    ["zh-cn"] = "'Warning' 警告输出",
    es = "Mensajes de 'Warning'",
    ru = "Вывод 'Warning'",
    ja = "'Warning' の出力",
  },
  output_mode_info = {
    en = "'Info' Output",
    ["zh-cn"] = "'Info' 信息输出",
    es = "Mensajes de 'Info'",
    ru = "Вывод 'Info'",
    ja = "'Info' の出力",
  },
  output_mode_debug = {
    en = "'Debug' Output",
    ["zh-cn"] = "'Debug' 调试输出",
    es = "Mensajes de 'Debug'",
    ru = "Вывод 'Debug'",
    ja = "'Debug' の出力",
  },
  output_disabled = {
    en = "Disabled",
    ["zh-cn"] = "禁用",
    es = "Desactivado",
    ru = "Выключен",
    ja = "無効",
  },
  output_log = {
    en = "Log",
    ["zh-cn"] = "日志",
    es = "Registro (log)",
    ru = "Лог",
    ja = "ログ",
  },
  output_chat = {
    en = "Chat",
    ["zh-cn"] = "聊天",
    es = "Chat",
    ru = "Чат",
    ja = "チャット",
  },
  output_notification = {
    en = "Notification",
    ["zh-cn"] = "通知",
    ru = "Уведомление",
    ja = "通知",
  },
  output_log_and_chat = {
    en = "Log & Chat",
    ["zh-cn"] = "日志与聊天",
    es = "Registro (log) y chat",
    ru = "Лог и чат",
    ja = "ログとチャット",
  },
  output_all = {
    en = "All",
    ["zh-cn"] = "全部",
    ru = "Все",
    ja = "すべて",
  },
  output_log_and_notification = {
    en = "Log & Notification",
    ["zh-cn"] = "日志与通知",
    ru = "Лог и Уведомление",
    ja = "ログと通知",
  },
  output_chat_and_notification = {
    en = "Chat & Notification",
    ["zh-cn"] = "聊天与通知",
    ru = "Чат и Уведомление",
    ja = "チャットと通知",
  },
  chat_history_enable = {
    en = "Chat Input History",
    ["zh-cn"] = "聊天输入历史",
    es = "Historial de chat",
    ru = "История ввода чата",
    ja = "チャット入力の履歴",
  },
  chat_history_enable_description = {
    en = "Saves all the messages and commands you typed in the chat window.\n\n" ..
         "You can browse your input history by opening the chat and pressing \"Arrow Up\" and \"Arrow Down\".",
    ["zh-cn"] = "保存你在聊天窗口输入过的所有消息和命令。\n" ..
        "\n" ..
        "打开聊天后按「上箭头」和「下箭头」即可浏览输入历史。",
    es = "Guarda todos los mensajes y comandos que escribas en la ventana de chat.\n\n" ..
         "Puedes navegar por tu historial de comandos abriendo el chat y usando las flechas del teclado.",
    ru = "Сохраняет все сообщения и команды, введённые в чате.\n\n" ..
         "Чтобы пролистывать историю ввода, откройте чат и используйте клавиши \"стрелка вверх\" и \"стрелка вниз\".",
    ja = "チャット欄に記入したすべてのメッセージとコマンドを保存します。\n\n" ..
         "入力履歴はチャットを開いて「上矢印」と「下矢印」キーで表示できます。",
  },
  chat_history_save = {
    en = "Save Input History Between Game Sessions",
    ["zh-cn"] = "跨游戏会话保存输入历史",
    es = "Guardar la entrada",
    ru = "Сохранять историю ввода между сеансами игры",
    ja = "ゲームセッション間での入力履歴の保存",
  },
  chat_history_save_description = {
    en = "Your chat input history will be saved even after reloading your game (or just DMF).",
    ["zh-cn"] = "即使重新加载游戏（或仅重载 DMF），你的聊天输入历史仍会被保存。",
    es = "El texto que introduzcas en el chat se guardara incluso al recargar el juego (o solo DMF)",
    ru = "Когда игрок выключает игру (или перезагружает DMF), DMF cохраняет историю ввода в файл настроек, чтобы загрузить её при следующем запуске игры.",
    ja = "ゲームの再起動 (またはDMFのリロード) 後もチャットの入力履歴が保持されます。",
  },
  chat_history_buffer_size = {
    en = "Input History Buffer Size",
    ["zh-cn"] = "输入历史缓冲区大小",
    es = "Número de comandos antiguos guardados",
    ru = "Размер буфера истории ввода",
    ja = "入力履歴のバッファサイズ",
  },
  chat_history_buffer_size_description = {
    en = "Maximum number of saved entries.\n\n" ..
         "WARNING: Changing this setting will erase your chat history.",
    ["zh-cn"] = "最多保存的记录条数。\n" ..
        "\n" ..
        "警告：更改此设置会清空你的聊天历史。",
    es = "Máximo número de comandos antiguos guardados.\n\n" ..
         "ATENCIÓN: Cambiar esta preferencia borra el historial del chat.",
    ru = "Максимальное количество сохраняемых записей.\n\n" ..
         "ВНИМАНИЕ: изменение этой настройки очистит вашу историю ввода.",
    ja = "履歴の最大保存数。\n\n" ..
         "警告：この設定を変更するとチャット履歴が消去されます。",
  },
  chat_history_remove_dups = {
    en = "Remove Duplicate Entries",
    ["zh-cn"] = "删除重复记录",
    es = "Eliminar lineas repetidas",
    ru = "Удалять повторяющиеся записи",
    ja = "重複する履歴の削除",
  },
  chat_history_remove_dups_mode = {
    en = "Removal Mode",
    ["zh-cn"] = "删除模式",
    es = "Modo de eliminación de repetidos",
    ru = "Режим удаления",
    ja = "削除方式",
  },
  chat_history_remove_dups_mode_description = {
    en = "Which duplicate entries should be removed.\n\n" ..
         "-- LAST --\nRemoves previous entry if it matches the last one.\n\n" ..
         "-- ALL --\nRemoves all entries if it matches the last one.",
    ["zh-cn"] = "选择要删除哪些重复记录。\n" ..
        "\n" ..
        "-- 仅上一条 --\n" ..
        "如果上一条与最新一条相同，则删除上一条。\n" ..
        "\n" ..
        "-- 全部 --\n" ..
        "如果记录与最新一条相同，则删除全部相同记录。",
    es = "Que lineas antiguas seran borradas cuando se escriba una nueva.\n\n" ..
        "-- ÚLTIMA --\nSolo la última, si es igual que la nueva.",
        "-- TODAS --\nTodas las lineas antiguas que sean iguales que la nueva. ",
    ru = "Повторяющиеся записи, которые будут удалены.\n\n" ..
         "-- ПОСЛЕДНИЕ --\nПредпоследняя запись будет удалена, если она совпадает с последней.\n\n" ..
         "-- ВСЕ --\nВсе записи, совпадающие с последней записью, будут удалены.",
    ja = "重複した際にどの履歴を削除するか。\n\n" ..
         "-- 直前 --\n直前の履歴が重複する場合、それを削除します。\n\n" ..
         "-- すべて --\n重複するすべての履歴を削除します。",
  },
  settings_last = {
    en = "Last",
    ["zh-cn"] = "仅上一条",
    es = "Última",
    ru = "Последние",
    ja = "直前",
  },
  settings_all = {
    en = "All",
    ["zh-cn"] = "全部",
    es = "Todas",
    ru = "Все",
    ja = "すべて",
  },
  chat_history_commands_only = {
    en = "Save only executed commands",
    ["zh-cn"] = "仅保存已执行的命令",
    es = "Salvar unicamente los comandos ejecutados",
    ru = "Сохранять только выполненные команды",
    ja = "実行したコマンドのみを保存",
  },
  chat_history_commands_only_description = {
    en = "Only successfully executed commands will be saved in the chat history.\n\n" ..
         "WARNING: Changing this setting will erase your chat history.",
    ["zh-cn"] = "只有成功执行的命令才会被保存到聊天历史中。\n" ..
        "\n" ..
        "警告：更改此设置会清空你的聊天历史。",
    es = "Solo los comandos ejecutados exitosamente serán salvados en el historial.\n\n" ..
         "ATENCIÓN: Cambiar esta preferencia borra el historial del chat.",
    ru = "Только успешно выполненные команды будут сохранены в истории ввода.\n\n" ..
         "ВНИМАНИЕ: изменение этой настройки очистит вашу историю ввода.",
    ja = "実行できたコマンドのみをチャット履歴に保存します。\n\n" ..
         "警告：この設定を変更するとチャット履歴が消去されます。",
  },

  chat_command_not_recognized = {
    en = "Command not recognized",
    ["zh-cn"] = "无法识别的命令",
    ru = "Команда не распознана",
    ja = "不明なコマンド",
  },
  clean_chat_history = {
    en = "cleans chat input history",
    ["zh-cn"] = "清除聊天输入历史",
    es = "Borra el historial de usuario",
    ru = "очищает историю ввода",
    ja = "チャット入力履歴の消去",
  },
  clean_chat_notifications = {
    en = "cleans chat notification alerts",
    ["zh-cn"] = "清除聊天通知提醒",
    ru = "очищает предупреждения об уведомлениях чата",
    ja = "チャット通知警告の消去",
  },
  dev_console_opened = {
    en = "Developer console opened.",
    ["zh-cn"] = "开发者控制台已打开。",
    es = "Abierto la consola de desarrollo.",
    ru = "Консоль разработчика открыта.",
    ja = "開発者コンソールを開きました。",
  },
  dev_console_closed = {
    en = "Developer console closed.",
    ["zh-cn"] = "开发者控制台已关闭。",
    es = "Cerrado la consola de desarrollo.",
    ru = "Консоль разработчика закрыта.",
    ja = "開発者コンソールを閉じました。",
  },
  dev_console_close_warning = {
    en = "The developer console is disabled, but must be closed manually.",
    ["zh-cn"] = "开发者控制台已禁用，但必须手动关闭。",
    ru = "Консоль разработчика отключена, но ее необходимо закрыть вручную.",
    ja = "開発者コンソールが無効になっていますが、手動で閉じる必要があります。",
  },


  -- MUTATORS

  mutator_no_description_provided = {
    en = "No description provided.",
    ["zh-cn"] = "未提供描述。",
    es = "No se proporcionó una descripción.",
    ru = "Описание не предоставлено.",
    ja = "説明がありません。",
  },

  -- Difficulties' names
  lowest = {
    en = "Sedition",
    ["zh-cn"] = "煽动",
    ru = "Мятеж",
    ja = "反乱",
  },
  low = {
    en = "Uprising",
    ["zh-cn"] = "暴乱",
    ru = "Восстание",
    ja = "アップライジング",
  },
  medium = {
    en = "Malice",
    ["zh-cn"] = "憎恶",
    ru = "Злоба",
    ja = "悪意",
  },
  high = {
    en = "Heresy",
    ["zh-cn"] = "异端",
    ru = "Ересь",
    ja = "異端",
  },
  highest = {
    en = "Damnation",
    ["zh-cn"] = "诅咒",
    ru = "Проклятие",
    ja = "破滅",
  },

  -- Chat messages
  broadcast_enabled_mutators = {
    en = "ENABLED MUTATORS",
    ["zh-cn"] = "已启用突变器",
    es = "MUTACIONES ACTIVADAS",
    ru = "МУТАТОРЫ ВКЛЮЧЕНЫ",
    ja = "ミューテーターが有効化されました",
  },
  broadcast_all_disabled = {
    en = "ALL MUTATORS DISABLED",
    ["zh-cn"] = "所有突变器已禁用",
    es = "TODAS LAS MUTACIONES DESACTIVADAS",
    ru = "ВСЕ МУТАТОРЫ ОТКЛЮЧЕНЫ",
    ja = "すべてのミューテーターが無効化されました",
  },
  broadcast_disabled_mutators = {
    en = "MUTATORS DISABLED",
    ["zh-cn"] = "突变器已禁用",
    es = "MUTACIONES DESACTIVADAS",
    ru = "МУТАТОРЫ ОТКЛЮЧЕНЫ",
    ja = "ミューテーターが無効化されました",
  },
  local_disabled_mutators = {
    en = "Mutators disabled",
    ["zh-cn"] = "突变器已禁用",
    es = "Mutaciones desactivadas",
    ru = "Мутаторы отключены",
    ja = "ミューテーターが無効化されました",
  },
  whisper_enabled_mutators = {
    en = "[Automated message] This lobby has the following mutators active",
    ["zh-cn"] = "[自动消息] 本大厅启用了以下突变器",
    es = "[Mensaje automático] Esta partida tiene las siguientes mutaciones",
    ru = "[Автоматическое сообщение] В этом лобби активны следующие мутаторы",
    ja = "[自動メッセージ] このロビーでは以下のミューテーターが有効になっています",
  },

  disabled_reason_not_server = {
    en = "because you're no longer the host",
    ["zh-cn"] = "因为你不再是主机",
    es = "porque ya no eres el anfitrión",
    ru = "потому что вы больше не хост",
    ja = "あなたがホストではなくなったため",
  },
  disabled_reason_difficulty_change = {
    en = "DUE TO CHANGE IN DIFFICULTY",
    ["zh-cn"] = "由于难度发生变化",
    es = "DEBIDO A UN CAMBIO DE DIFICULTAD",
    ru = "ИЗ-ЗА ИЗМЕНЕНИЯ СЛОЖНОСТИ",
    ja = "難易度が変更されたため",
  },

  -- Interface
  mutators_title = {
    en = "Mutators",
    ["zh-cn"] = "突变器",
    es = "Mutaciones",
    ru = "Мутаторы",
    ja = "ミューテーター",
  },
  mutators_banner_description = {
    en = "Enable and disable mutators",
    ["zh-cn"] = "启用和禁用突变器",
    es = "Activa y desactiva las mutaciones",
    ru = "Включить и отключить мутаторы",
    ja = "ミューテーターのオン/オフ",
  },
  no_mutators = {
    en = "No mutators installed",
    ["zh-cn"] = "未安装突变器",
    es = "No hay mutaciones instaladas",
    ru = "Нет установленных мутаторов",
    ja = "ミューテーターがインストールされていません",
  },
  no_mutators_description = {
    en = "Subscribe to mods and mutators on the workshop",
    ["zh-cn"] = "在创意工坊订阅模组和突变器",
    es = "Subscribete a mutaciones en el Steam Workshop",
    ru = "Подпишитесь на моды и мутаторы в мастерской Steam",
    ja = "ワークショップでModやミューテーターをサブスクライブしてください",
  },

  -- Mutator widgets' tooltips
  tooltip_incompatible_mutators = {
    en = "\n\n-- INCOMPATIBLE WITH MUTATORS --\n",
    ["zh-cn"] = "\n" ..
        "\n" ..
        "-- 与突变器不兼容 --\n" ..
        "",
    es = "\n\n-- INCOMPATIBLE CON LAS MUTACIONES --\n",
    ru = "\n\n-- НЕСОВМЕСТИМО С МУТАТОРАМИ --\n",
    ja = "\n\n-- ミューテーターと互換性なし --\n",
  },
  tooltip_compatible_mutators = {
    en = "\n\n-- COMPATIBLE ONLY WITH MUTATORS --\n",
    ["zh-cn"] = "\n" ..
        "\n" ..
        "-- 仅兼容突变器 --\n" ..
        "",
    es = "\n\n-- COMPATIBLE CON LAS MUTACIONES --\n",
    ru = "\n\n-- СОВМЕСТИМО ТОЛЬКО С МУТАТОРАМИ --\n",
    ja = "\n\n-- ミューテーターとのみ互換性あり",
  },
  tooltip_compatible_with_all_mutators = {
    en = "\n\n-- COMPATIBLE WITH ALL MUTATORS --",
    ["zh-cn"] = "\n" ..
        "\n" ..
        "-- 与所有突变器兼容 --",
    es = "\n\n-- COMPATIBLE CON TODAS LAS MUTACIONES --",
    ru = "\n\n-- СОВМЕСТИМО СО ВСЕМИ МУТАТОРАМИ --\n",
    ja = "\n\n-- すべてのミューテーターと互換性あり --\n",
  },
  tooltip_incompatible_with_all_mutators = {
    en = "\n\n-- INCOMPATIBLE WITH ALL MUTATORS --",
    ["zh-cn"] = "\n" ..
        "\n" ..
        "-- 与所有突变器不兼容 --",
    es = "\n\n-- INCOMPATIBLE CON TODAS LAS MUTACIONES --",
    ru = "\n\n-- НЕСОВМЕСТИМО СО ВСЕМИ МУТАТОРАМИ --\n",
    ja = "\n\n-- すべてのミューテーターと互換性なし --\n",
  },

  tooltip_incompatible_diffs = {
    en = "\n\n-- INCOMPATIBLE WITH DIFFICULTIES --\n",
    ["zh-cn"] = "\n" ..
        "\n" ..
        "-- 与难度不兼容 --\n" ..
        "",
    es = "\n\n-- INCOMPATIBLE CON LAS DIFICULTADES --\n",
    ru = "\n\n-- НЕСОВМЕСТИМО СО СЛОЖНОСТЯМИ --\n",
    ja = "\n\n-- 難易度と互換性なし --\n",
  },
  tooltip_compatible_diffs = {
    en = "\n\n-- COMPATIBLE ONLY WITH DIFFICULTIES --\n",
    ["zh-cn"] = "\n" ..
        "\n" ..
        "-- 仅兼容难度 --\n" ..
        "",
    es = "\n\n-- COMPATIBLE CON LAS DIFICULTADES --\n",
    ru = "\n\n-- СОВМЕСТИМО ТОЛЬКО СО СЛОЖНОСТЯМИ --\n",
    ja = "\n\n-- 難易度とのみ互換性あり --\n",
  },
  tooltip_compatible_with_all_diffs = {
    en = "\n\n-- COMPATIBLE WITH ALL DIFFICULTIES --",
    ["zh-cn"] = "\n" ..
        "\n" ..
        "-- 与所有难度兼容 --",
    es = "\n\n-- COMPATIBLE CON TODAS LAS DIFICULTADES --",
    ru = "\n\n-- СОВМЕСТИМО СО ВСЕМИ СЛОЖНОСТЯМИ --\n",
    ja = "\n\n-- すべての難易度と互換性あり --\n",
  },

  tooltip_conflicts = {
    en = "\n\n-- CONFLICTS --\n",
    ["zh-cn"] = "\n" ..
        "\n" ..
        "-- 冲突 --\n" ..
        "",
    es = "\n\n-- CONFLICTOS --\n",
    ru = "\n\n-- КОНФЛИКТЫ --\n",
    ja = "\n\n-- 競合 --\n",
  },

  tooltip_append_mutator = {
    en = " (mutator)",
    ["zh-cn"] = "（突变器）",
    es = " (mutacion)",
    ru = " (мутатор)",
    ja = " (ミューテーター)",
  },
  tooltip_append_difficulty = {
    en = " (difficulty)",
    ["zh-cn"] = "（难度）",
    es = " (dificultad)",
    ru = " (сложность)",
    ja = " (難易度)",
  },
}

