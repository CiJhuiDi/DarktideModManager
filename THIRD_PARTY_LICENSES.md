# 第三方组件许可说明（THIRD_PARTY_LICENSES）

本软件（Darktide Mod Manager）主程序以 [MIT 协议](LICENSE) 发布。
以下内置组件来自第三方开源项目，随本软件按各自许可证条款分发：

| 组件 | 打包位置 | 上游项目 | 许可证 |
| --- | --- | --- | --- |
| Darktide Mod Framework（加载器 + mods/base + mods/dmf） | `dmf_payload/mods/` | [Darktide-Mod-Framework/Darktide-Mod-Framework](https://github.com/Darktide-Mod-Framework/Darktide-Mod-Framework) | MIT |
| dtkit-patch（补丁工具） | `dmf_payload/tools/dtkit-patch.exe` | [ManShanko/dtkit-patch](https://github.com/ManShanko/dtkit-patch) | MIT OR Apache-2.0（本项目按 MIT 条款再分发） |
| dt-mod-autopatch（自动装载插件） | `dmf_payload/binaries/plugins/_dt_mod_autopatch.dll` | [ManShanko/dt-mod-autopatch](https://github.com/ManShanko/dt-mod-autopatch) | MIT |

> 注：致谢中提到的 [xsSplater/Darktide_laucher_bypass](https://github.com/xsSplater/Darktide_laucher_bypass)（GPL-3.0）仅作参考致谢，**未随本软件分发**，故本软件不承担 GPL 分发义务。

## 组件版权声明

- Darktide Mod Framework：Copyright (c) 2018 Vermintide Mod Framework
- dtkit-patch：Copyright (c) 2022 manshanko（亦可在 Apache-2.0 条款下使用，见上游仓库 LICENSE-APACHE）
- dt-mod-autopatch：Copyright (c) 2025 manshanko

## MIT License（适用于上述所有 MIT 组件）

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
