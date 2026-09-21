# Python 语音对话演示

这是本项目的 Python 端程序，提供文字或麦克风输入、大模型问答、本地日期/天气查询、动作识别、位图预览，以及可选的串口输出。

> 项目目录名保留了 `qwen` 历史名称；当前 Python 默认配置实际调用的是智谱 `GLM-4-Flash` 接口。更换模型或服务时，请同步修改 API 地址、鉴权方式和返回 JSON 解析。

## 文件说明

```text
├─ qwen_pc_demo.py                 # 核心逻辑与命令行程序
├─ qwen_chat_gui_final.py          # Tk 图形界面
├─ local_queries.py                # 本地日期、天气等辅助查询
├─ local_api_config.example.py     # API Key 配置模板
├─ requirements.txt                # Python 依赖
├─ install_pc.bat                  # Windows 安装脚本
└─ run_pc_demo.bat                 # Windows 启动脚本
```

## 快速运行

1. 安装 Python 3.10 或更高版本。Windows 建议使用 Python 3.12；如果 `PyAudio` 安装失败，请先检查 Python 版本和音频驱动。
2. 复制 `local_api_config.example.py` 为 `local_api_config.py`，只在本机填写 API Key；也可以设置环境变量 `BIGMODEL_API_KEY`。
3. 安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. 启动图形界面：

   ```powershell
   python qwen_chat_gui_final.py
   ```

   也可以运行命令行版本：

   ```powershell
   python qwen_pc_demo.py --help
   ```

Windows 用户还可以双击 `install_pc.bat` 安装依赖，再双击 `run_pc_demo.bat` 启动。

未指定串口时，命令行程序使用模拟串口，因此可以只在电脑上进行文字或麦克风问答测试。

## 安全提示

不要把真实 API Key 提交到 GitHub。仓库通过 `.gitignore` 排除了 `local_api_config.py`，只保留模板文件。如果 Key 曾经出现在公开仓库、截图或日志中，应立即撤销并重新生成。

