# STM32 移植文件

本目录提供与电脑上位机配套的、与具体 HAL/厂商无关的协议文件。它不是对原始 Keil 工程的替代，而是迁移到其他 STM32、GD32 或裸机 UART 工程时可直接复制的最小协议层。

## 文件

- `include/pc_demo_protocol.h`：波特率、缓冲区、图片限制、动作枚举和解析函数声明。
- `src/pc_demo_protocol.c`：解析 `@CMD:<ACTION>;TEXT:<reply>` 文本帧的参考实现。
- `protocol.md`：完整串口帧格式、时序和迁移注意事项。

## 接入步骤

```c
#include "pc_demo_protocol.h"

pc_demo_action_t action;
if (pc_demo_parse_cmd(rx_line, rx_len, &action)) {
    // 根据 action 控制 LCD、电机或其他外设
    uart_write("OK\\r\\n", 4);
} else {
    uart_write("ERR\\r\\n", 5);
}
```

图片帧不建议在中断里绘制。中断只接收数据并置位完成标志，主循环校验尺寸后再刷新 LCD。

