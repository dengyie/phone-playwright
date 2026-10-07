# Phone-Playwright 输入子系统工程规格书 (Tri-Channel Input Subsystem)

## 1. 业务痛点与技术挑战

在移动端自动化中，文本输入（特别是中文、Emoji、多音字及特殊标点符号）是失败率最高的环节。核心难点包括：
1. **Shell `input text` 的固有缺陷**：仅映射为底层 Linux Keycode，无法支持非 ASCII 字符，且空格和 Shell 元字符（`&`, `|`, `'`, `"`, `$`, `\`）会引发解析截断或进程崩溃。
2. **Android 10+ 定制 ROM 与云手机限制**：部分 ROM（如定制云手机、MIUI、ColorOS、EMUI）在 Shell 层面禁用了 `cmd clipboard set text` 广播命令，直接返回 `No shell command implementation.` 或静默空转。
3. **输入法焦点与追加污染**：传统自动化工具未严格执行清空替换语义，导致多次输入发生内容累加；部分模拟器下 `input keycombination 113 29` (Ctrl+A) 会丢失修饰键并键入裸字符 `'a'`。

---

## 2. 三阶安全输入架构 (Tri-Channel Architecture)

为保证在**任何异构设备**（Pixel、三星 Fold 云手机、小米、OnePlus、MuMu 模拟器、iOS）上均能 100% 成功输入且不产生假阳性，`phone-playwright` 采用自愈阶梯式 **Tri-Channel 输入架构**。

```
                    [type_text(payload)]
                             |
                   +---------+---------+
                   | payload 是纯 ASCII?|
                   +---------+---------+
                        /          \
                     Yes            No (含中文/Unicode/Emoji)
                     /                \
          +-----------------+    +-----------------------------+
          | Channel 3 (ASCII)|    | 尝试 Channel 1 (原生剪贴板广播)|
          | 严格 Shell 转义  |    | cmd clipboard set text      |
          | input text %s    |    +-----------------------------+
          +-----------------+                  |
                                         (检查执行回执)
                                               |
                                     +---------+---------+
                                     | 回执含不支持标记?  |
                                     | ("No shell cmd")  |
                                     +---------+---------+
                                          /          \
                                       Yes            No
                                       /                \
                       +----------------------+    +-------------------------+
                       | Channel 2 (AdbIME)   |    | 下发粘贴键码 KEYCODE 279|
                       | 探测/启用 AdbIME     |    +-------------------------+
                       | am broadcast -a ...  |                  |
                       | ADB_INPUT_B64 <b64>  |          +-------+-------+
                       +----------------------+          | 无障碍树终态校验 |
                                  |                      +-------+-------+
                       +----------+----------+               /         \
                       | 无障碍树终态检索校验   |            Pass        Fail
                       +---------------------+              /             \
                                  |                     (成功)      +---------------+
                               /     \                              | 补发一次 Ctrl+V|
                            Pass     Fail                           +---------------+
                            /           \                                  |
                        (成功)     +---------------------+          +-------+-------+
                                   | 抛出强类型异常       |          | 无障碍树二次校验 |
                                   | PhonePlaywrightError|          +-------+-------+
                                   | (附带可操作修复建议)  |               /         \
                                   +---------------------+            Pass        Fail
                                                                      /              \
                                                                  (成功)       (转入 Channel 2)
```

---

## 3. 详细通道技术实现

### 3.1 Channel 1: 原生剪贴板通道 (Native Clipboard Broadcast)
* **适用场景**：原生 Android 11+、OnePlus、Google Pixel、通用标准真机。
* **执行步骤**：
  1. 通过 `shlex.quote(text)` 转义字符，执行 `cmd clipboard set text '<quoted_text>'`。
  2. 探测返回输出：若包含 `("no shell command implementation", "unknown command", "not implemented")`，直接标记 Channel 1 失效并转入 Channel 2。
  3. 若无错误标记，执行 `input keyevent 279`（`KEYCODE_PASTE`）。
  4. 触发无障碍树检索 `_tree_contains_text(payload)`：
     - 若命中：完成输入。
     - 若未命中且通道可用：尝试补发一次组合键 `input keycombination 113 47`（`CTRL_LEFT + V`）。

### 3.2 Channel 2: AdbIME 虚拟输入法 Base64 广播通道 (IME Broadcast Tunnel)
* **适用场景**：三星云手机、华为云手机、定制 ARM 云机、剪贴板严格限制的 ROM。
* **核心协议**：
  1. **输入法状态探测**：
     - 执行 `settings get secure default_input_method`，探测当前激活输入法。
     - 执行 `ime list -s`，检查系统已安装的输入法列表。
  2. **自动热切换与恢复 (Hot-Swap IME Context)**：
     - 若发现 `com.android.adbkeyboard/.AdbIME` 未激活，执行 `ime enable com.android.adbkeyboard/.AdbIME` + `ime set com.android.adbkeyboard/.AdbIME`。
     - 记录用户原输入法（如 `com.sohu.inputmethod.sogou/.SogouIME`），在会话销毁或调用 `driver.disconnect()` 时自动还原。
  3. **Base64 编码广播分发**：
     - 将 Unicode 文本编码为 UTF-8 Base64：`B64 = base64.b64encode(text.encode('utf-8')).decode('ascii')`。
     - 发送系统广播：`am broadcast -a ADB_INPUT_B64 --es msg '<B64>'`。
     - 该广播绕过所有剪贴板权限限制，直接注入至当前焦点 `InputConnection.commitText()`。

### 3.3 Channel 3: 严格转义 ASCII 快速通道 (Strictly Escaped ASCII)
* **适用场景**：纯英文、数字、URL、基础命令。
* **转义算法**：
  ```python
  def escape_android_ascii(text: str) -> str:
      """对 ASCII 字符做严格转义，空格替换为 %s，Shell 元字符逐字符添加反斜杠。"""
      escaped = []
      for char in text:
          if char == " ":
              escaped.append("%s")
          elif char in "\\\"'&*()~`!#$|;<>[]{}":
              escaped.append(f"\\{char}")
          else:
              escaped.append(char)
      return "".join(escaped)
  ```
  执行命令：`input text <escaped_text>`。耗时仅需 $\approx 10\text{ms}$。

---

## 4. 替换清空语义规范 (Replace Clear Semantics)

Playwright 的 `fill(text)` 契约要求：**清除现有内容并替换为新内容**，而非在尾部追加。

### 4.1 为什么禁用 `Ctrl+A` (KEYCODE 113 + KEYCODE 29)？
* **实测问题**：在 MuMu 12 等模拟器及部分低端真机上，底层 Linux 驱动无法正确维持 `CTRL_LEFT` 的持续按下状态，`input keycombination 113 29` 退化为单独键入字母 `'a'`，导致输入框被输入字符 `'a'` 污染。

### 4.2 确定性物理清空方案 (`clear_text`)
采用无修饰键依赖的组合 Keyevent 序列：
1. **光标移至末尾**：`KEYCODE_MOVE_END (123)`。
2. **批量连发退格**：连发 100 次 `KEYCODE_DEL (67)`。
3. **单行合并下发**：
   ```bash
   input keyevent 123 67 67 67 67 67 67 67 67 67 67 ... (共 101 个参数)
   ```
* **特性**：
  - 单次 ADB 往返即可完成，总耗时 $< 30\text{ms}$。
  - 在空字段或短字段上，多余的 `DEL` 键由系统丢弃，无任何副作用。

---

## 5. 异常防护与行为契约

| 场景 | 系统响应 | 错误类型 | 修复指引 |
|---|---|---|---|
| **剪贴板广播失败 + 无 AdbIME** | 阻断并显式抛错 | `PhonePlaywrightError` | 提示设备剪贴板被禁用，指导安装 AdbIME 或开启宿主剪贴板同步 |
| **文本注入后树中检索不到** | 阻断并显式抛错 | `PhonePlaywrightError` | 提示输入控件可能未获得焦点或不可编辑，禁止假阳性成功 |
| **输入控件只读 (`editable=False`)** | 状态机在前置阶段拦截 | `ActionTimeoutError` | 提示目标控件非可输入组件 |
