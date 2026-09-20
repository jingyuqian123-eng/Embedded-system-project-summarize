# Qwen PC Demo / STM32 语音动作显示系统

这是一个“电脑上位机 + STM32 LCD 终端”的语音交互演示工程。电脑负责录音、语音识别、云端大模型请求和位图渲染，STM32 负责按键、串口收发和 LCD 显示。

> 项目目录名保留了 `qwen` 历史名称；当前 Python 默认配置实际调用的是智谱 `GLM-4-Flash` 接口。更换模型或服务时，请同步修改 API 地址、鉴权方式和返回 JSON 解析。

## 功能

- 电脑麦克风录音，按住开发板 KEY0 说话、松开后提交识别。
- 电脑调用语音识别服务，再调用大模型判断动作：`FORWARD`、`BACK`、`LEFT`、`RIGHT`、`STOP`、`NONE`。
- 电脑把回答和方向图标渲染为 1-bit 黑白位图，通过 USART1 发送到 STM32。
- STM32F407 通过 LCD 显示回答和动作，并把 KEY0 事件回传给电脑。
- 支持设备分辨率查询、文本动作帧、位图帧和简单 ACK（`OK`/`ERR`）。

## 目录

```text
qwen_pc_demo/
├─ qwen_pc_demo.py                 # 上位机核心：API、录音、串口、位图
├─ qwen_chat_gui_final.py          # Tk GUI
├─ local_queries.py                # 本地天气等辅助查询
├─ requirements.txt
├─ install_pc.bat / run_pc_demo.bat
├─ local_api_config.example.py     # API Key 模板（真实 Key 不提交）
├─ 实验X 语音动作显示实验/          # STM32F407 Keil 工程与驱动
├─ stm32_porting/                  # 可移植协议头文件、示例实现和说明
├─ docs/                           # 配套说明
└─ 新手教程与答辩问答.md
```

## 快速运行

1. 安装 Python 3.10+。Windows 上建议使用 Python 3.12；`PyAudio` 安装失败时优先检查 Python 版本和音频驱动。
2. 复制 `local_api_config.example.py` 为 `local_api_config.py`，只在本机填写 API Key；也可以设置环境变量 `BIGMODEL_API_KEY`。
3. 安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. 将开发板 USB-UART 接到电脑，确认波特率为 `115200`，并在程序中选择正确 COM 口。
5. 运行：

   ```powershell
   python qwen_chat_gui_final.py
   ```

   命令行版本可直接运行 `python qwen_pc_demo.py --help` 查看参数。

## STM32 端

STM32 工程目标芯片是 `STM32F407ZGTx`，USART1 使用 PA9/PA10，LCD 和 KEY0 引脚以工程中的 BSP 配置为准。USB-UART 只负责运行时串口通信，不能替代 ST-Link/J-Link/CMSIS-DAP 下载器。

协议、移植步骤和可复制的 C 文件见 [`stm32_porting/`](stm32_porting/README.md)；原始 Keil 工程见 [`实验X 语音动作显示实验/`](实验X%20语音动作显示实验/)。

## 安全提示

不要把真实 API Key 提交到 GitHub。仓库通过 `.gitignore` 排除了 `local_api_config.py`，只保留模板文件。如果 Key 曾经出现在公开仓库、截图或日志中，应立即撤销并重新生成。

