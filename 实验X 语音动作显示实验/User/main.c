/**
 ****************************************************************************************************
 * @file        main.c
 * @author      ����ԭ���Ŷ�(ALIENTEK)
 * @version     V1.0
 * @date        2021-10-14
 * @brief       ���ڶ�����ʾ ʵ��
 * @license     Copyright (c) 2020-2032, �������������ӿƼ����޹�˾
 ****************************************************************************************************
 * @attention
 *
 * ʵ��ƽ̨:����ԭ�� ̽���� F407������
 * ������Ƶ:www.yuanzige.com
 * ������̳:www.openedv.com
 * ��˾��ַ:www.alientek.com
 * �����ַ:openedv.taobao.com
 *
 ****************************************************************************************************
 */

#include "./SYSTEM/sys/sys.h"
#include "./SYSTEM/usart/usart.h"
#include "./SYSTEM/delay/delay.h"
#include "./BSP/LED/led.h"
#include "./BSP/LCD/lcd.h"
#include <string.h>
#include <stdio.h>

typedef enum
{
    ACTION_NONE, ACTION_FORWARD, ACTION_BACK,
    ACTION_LEFT, ACTION_RIGHT, ACTION_STOP
} action_t;

static const char *const action_names[] =
{
    "NONE", "FORWARD", "BACK", "LEFT", "RIGHT", "STOP"
};

/* ʹ����Ļʵ�ʳߴ磬ͼ�κ�������������Ļ����Ϊ��׼�� */
static void display_action(action_t action)
{
    uint16_t width = lcddev.width;
    uint16_t size = 48;
    uint16_t cx = width - 24, cy = 24;
    uint16_t length = size / 3, area = size * 2 / 3;
    uint16_t half = length / 2, head = length / 4;
    uint16_t x, y, color;
    char status[20];

    if (size < 32) return;
    x = cx - area / 2;
    y = cy - area / 2;
    lcd_fill(x, y, x + area - 1, y + area - 1, BLACK);
    switch (action)
    {
        case ACTION_FORWARD:
        case ACTION_BACK:
            color = YELLOW;
            y = action == ACTION_FORWARD ? cy - half : cy + half;
            lcd_draw_line(cx, cy - half, cx, cy + half, color);
            lcd_draw_line(cx - head, cy, cx, y, color);
            lcd_draw_line(cx + head, cy, cx, y, color);
            break;
        case ACTION_LEFT:
        case ACTION_RIGHT:
            color = YELLOW;
            x = action == ACTION_LEFT ? cx - half : cx + half;
            lcd_draw_line(cx - half, cy, cx + half, cy, color);
            lcd_draw_line(cx, cy - head, x, cy, color);
            lcd_draw_line(cx, cy + head, x, cy, color);
            break;
        case ACTION_STOP:
            x = cx - half / 2;
            y = cy - half / 2;
            lcd_fill(x, y, x + half - 1, y + half - 1, RED);
            break;
        default:
            break;
    }
    lcd_fill(0, 10, width - 49, 25, BLACK);
    sprintf(status, "CMD: %s", action_names[action]);
    lcd_show_string(10, 10, width - 58, 16, 16, status, WHITE);
}

/* ���ջ�����û���ַ�����ֹ�������ж�ȡ���� len Ϊ�߽硣 */
static void parse_and_display(const uint8_t *buf, uint16_t len)
{
    uint16_t split, text_start, action_len, i;
    action_t action = ACTION_NONE;

    if (len < 11 || len > USART_REC_LEN ||
        strncmp((const char *)buf, "@CMD:", 5) != 0) return;

    for (split = 5; split + 6 <= len; ++split)
    {
        if (strncmp((const char *)buf + split, ";TEXT:", 6) == 0) break;
    }
    if (split + 6 > len) return;

    action_len = split - 5;
    for (i = 0; i < sizeof(action_names) / sizeof(action_names[0]); ++i)
    {
        if (action_len == strlen(action_names[i]) &&
            strncmp((const char *)buf + 5, action_names[i], action_len) == 0)
        {
            action = (action_t)i;
            break;
        }
    }
    text_start = split + 6;
    display_action(action);
    /* ���ֽڻ��� GBK������ %s Խ�缰��ʽ�ַ������͡� */
    for (i = text_start; i < len; ++i) printf("%c", (int)buf[i]);
    printf("\r\n");
}


/* Text is rasterized on the PC, so no external Chinese font is needed. */
static int hex_value(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

#define MAX_IMG_WIDTH 480
static void key0_init(void)
{
    GPIO_InitTypeDef g={0}; __HAL_RCC_GPIOE_CLK_ENABLE(); g.Pin=GPIO_PIN_4; g.Mode=GPIO_MODE_INPUT; g.Pull=GPIO_PULLUP; g.Speed=GPIO_SPEED_FREQ_LOW; HAL_GPIO_Init(GPIOE,&g);
}
static void key0_poll(void)
{
    static uint8_t stable=0,last=0; static uint32_t tick=0; uint8_t raw=(HAL_GPIO_ReadPin(GPIOE,GPIO_PIN_4)==GPIO_PIN_RESET); uint32_t now=HAL_GetTick();
    if(raw!=last){last=raw;tick=now;} else if(now-tick>=20 && raw!=stable){stable=raw; printf(raw?"@BTN:DOWN\r\n":"@BTN:UP\r\n");}
}
static void lcd_show_bitmap_1bpp(uint16_t x,uint16_t y,uint16_t w,uint16_t h,const uint8_t *data)
{
    static uint16_t line[MAX_IMG_WIDTH]; uint16_t r,c; uint16_t rb=(w+7)/8;
    if (w>MAX_IMG_WIDTH) return;
    for(r=0;r<h;r++){ for(c=0;c<w;c++) line[c]=(data[r*rb+c/8]&(0x80>>(c%8)))?WHITE:BLACK; lcd_color_fill(x,y+r,x+w-1,y+r,line); }
}
static int handle_img_header(const uint8_t *buf,uint16_t len)
{
    char h[64]; unsigned int w,hh,n,x,y; uint32_t start;
    if(len>=sizeof(h)) return 0; memcpy(h,buf,len); h[len]=0;
    if(sscanf(h,"@IMG:%ux%u;LEN:%u;X:%u;Y:%u",&w,&hh,&n,&x,&y)!=5) return 0;
    if(w==0||hh==0||w>MAX_IMG_WIDTH||n!=((w+7)/8)*hh||n>MAX_IMG_BYTES) return 0;
    if(x >= lcddev.width || y >= lcddev.height || x+w > lcddev.width || y+hh > lcddev.height) return 0;
    g_rx_mode=RX_MODE_IMG; g_img_rx_done=0;
    /* The RX ISR unconditionally re-arms a 1-byte line-mode receive after
     * every completed byte, including the '\n' that just finished this
     * "@IMG:...\r\n" header line. That leaves USART1's RxState BUSY, so the
     * HAL_UART_Receive_IT() call below would be silently rejected
     * (HAL_BUSY) and g_img_buf would never actually get filled -- the
     * first payload byte instead completes that stale 1-byte receive and
     * (since g_rx_mode is already RX_MODE_IMG) marks g_img_rx_done after
     * just 1 byte, so the still-all-zero g_img_buf gets shown as a solid
     * background-color block. Abort that stale pending receive first so
     * RxState goes back to READY and the real n-byte image receive can
     * start. */
    HAL_UART_AbortReceive_IT(&g_uart1_handle);
    HAL_UART_Receive_IT(&g_uart1_handle,g_img_buf,n);
    start=HAL_GetTick(); while(!g_img_rx_done && HAL_GetTick()-start<1500){}
    if(g_img_rx_done) lcd_show_bitmap_1bpp((uint16_t)x,(uint16_t)y,(uint16_t)w,(uint16_t)hh,g_img_buf);
    g_rx_mode=RX_MODE_LINE; g_usart_rx_sta=0; HAL_UART_Receive_IT(&g_uart1_handle,(uint8_t*)g_rx_buffer,RXBUFFERSIZE); return g_img_rx_done?1:0;
}
static int process_frame(const uint8_t *buf, uint16_t len)
{
    char line[USART_REC_LEN + 1];
    unsigned int x, y;
    int offset = 0;
    uint16_t i, bit, count;
    unsigned int value, px;
    if (len > USART_REC_LEN) return 0;
    memcpy(line, buf, len);
    line[len] = 0;
    if (len == 6 && memcmp(line, "@HELLO", 6) == 0) return 2;
    if (len == 9 && memcmp(line, "@ICON:SUN", 9) == 0)
    {
        uint16_t cx = lcddev.width / 2, cy = lcddev.height - 70;
        uint8_t r = lcddev.width < lcddev.height ? 14 : 18;
        lcd_fill(0, 0, lcddev.width - 1, 47, BLACK);
        lcd_fill_circle(cx, cy, r / 2, YELLOW);
        lcd_draw_circle(cx, cy, r / 2, YELLOW);
        lcd_draw_line(cx, cy - r, cx, cy - r / 2, YELLOW);
        lcd_draw_line(cx, cy + r / 2, cx, cy + r, YELLOW);
        lcd_draw_line(cx - r, cy, cx - r / 2, cy, YELLOW);
        lcd_draw_line(cx + r / 2, cy, cx + r, cy, YELLOW);
        return 1;
    }
    if (len == 5 && memcmp(line, "@PAGE", 5) == 0)
    {
        lcd_fill(0, 0, lcddev.width - 1, lcddev.height - 1, BLACK);
        return 1;
    }
    if (len >= 5 && memcmp(line, "@ROW:", 5) == 0)
    {
        if (sscanf(line + 5, "%u,%u,%n", &x, &y, &offset) != 2 || offset <= 0) return 0;
        offset += 5;
        if (offset >= len || x >= lcddev.width || y >= lcddev.height) return 0;
        count = len - offset;
        if (count > 64 || (count & 1)) return 0;
        if (x + (count / 2) * 8 > lcddev.width + 7U) return 0;
        for (i = 0; i < count; ++i)
            if (hex_value(line[offset + i]) < 0) return 0;
        for (i = 0; i < count; i += 2)
        {
            value = (hex_value(line[offset + i]) << 4) | hex_value(line[offset + i + 1]);
            for (bit = 0; bit < 8; ++bit)
            {
                px = x + (i / 2) * 8 + bit;
                if (px < lcddev.width)
                    lcd_draw_point(px, y, (value & (0x80U >> bit)) ? WHITE : BLACK);
            }
        }
        return 1;
    }
    if (len >= 11 && memcmp(line, "@CMD:", 5) == 0 && strstr(line + 5, ";TEXT:") != NULL)
    {
        parse_and_display(buf, len);
        return 1;
    }
    return 0;
}

int main(void)
{
    uint16_t len;
    int response;
    HAL_Init();
    sys_stm32_clock_init(336, 8, 2, 7);
    delay_init(168);
    usart_init(115200);
    led_init();
    lcd_init();
    key0_init();
    g_back_color = BLACK;
    lcd_clear(BLACK);
    display_action(ACTION_NONE);
    printf("@DEV:%ux%u\r\n", (unsigned int)lcddev.width, (unsigned int)lcddev.height);

    while (1)
    {
        key0_poll();
        if (g_usart_rx_sta & 0x8000)
        {
            len = g_usart_rx_sta & 0x3FFF;
            if (len >= 5 && memcmp(g_usart_rx_buf, "@IMG:", 5) == 0)
                response = handle_img_header(g_usart_rx_buf, len);
            else if (len >= 8 && memcmp(g_usart_rx_buf, "@REQ:DEV", 8) == 0)
            {
                printf("@DEV:%ux%u\r\n", (unsigned int)lcddev.width, (unsigned int)lcddev.height);
                response = 1;
            }
            else
                response = process_frame(g_usart_rx_buf, len);
            /* ��Ч����Ч֡�������ͷŽ������� */
            g_usart_rx_sta = 0;
            if (response == 2) printf("SIZE:%u,%u\r\n", (unsigned int)lcddev.width, (unsigned int)lcddev.height);
            else printf(response ? "OK\r\n" : "ERR\r\n");
        }
    }
}
