#include <stdio.h>
#include <inttypes.h>
#include <string.h>
#include <time.h>
#include <sys/time.h>
#include <stdlib.h>
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_sntp.h"
#include "esp_mac.h"
#include "nvs_flash.h"
#include "driver/uart.h"
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

#include "wifi_secrets.h"

#define UART_NUM UART_NUM_0
#define BUF_SIZE (1024)
#define UART_BUF_SIZE (1024 * 2)
#define CMD_BUF_SIZE (BUF_SIZE * 2)

static const char *TAG = "ESP-Monitor";

// WiFi 연결 이벤트 그룹
static EventGroupHandle_t s_wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0

// 누적 버퍼: 청크로 쪼개져 들어오는 명령도 줄 단위로 인식
static char cmd_buf[CMD_BUF_SIZE];
static size_t cmd_buf_len = 0;

// 리부트 플래그 (태스크 간 통신용)
static volatile bool reboot_requested = false;

static void process_one_line(char *line) {
    while (*line == ' ' || *line == '\r' || *line == '\n') line++;
    size_t L = strlen(line);
    while (L > 0 && (line[L - 1] == '\r' || line[L - 1] == '\n')) line[--L] = '\0';
    if (L == 0) return;

    printf("[PROCESS] Line: '%s'\n", line);

    if (strstr(line, "REBOOT")) {
        reboot_requested = true;
        printf("[PROCESS] Reboot requested\n");
    }
}

// --- WiFi 이벤트 핸들러 ---
static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                                int32_t event_id, void *event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        printf("[WIFI] Disconnected, retrying...\n");
        esp_wifi_connect();
        xEventGroupClearBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        printf("[WIFI] Connected! IP: " IPSTR "\n", IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static void wifi_init_sta(void) {
    s_wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                    &wifi_event_handler, NULL, &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                    &wifi_event_handler, NULL, &instance_got_ip));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = WIFI_SSID,
            .password = WIFI_PASS,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    printf("[WIFI] Connecting to %s...\n", WIFI_SSID);
}

// --- NTP 시간 동기화 ---
static void initialize_sntp(void) {
    printf("[NTP] Initializing SNTP...\n");
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_init();
}

static void wait_for_time_sync(void) {
    // 1. 현재 시간 확인 (이미 유효한지 체크)
    time_t now;
    struct tm timeinfo;
    time(&now);
    localtime_r(&now, &timeinfo);
    
    // 2025년 이후라면 이미 동기화된 것으로 간주 (불필요한 대기 스킵)
    if (timeinfo.tm_year >= (2025 - 1900)) {
        printf("[NTP] Time is already set (%04d-%02d-%02d). Skipping sync wait.\n", 
               timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday);
        fflush(stdout);
        return;
    }

    printf("[NTP] Waiting for time sync...\n");
    fflush(stdout);

    int retry = 0;
    const int max_retry = 30;
    while (esp_sntp_get_sync_status() == SNTP_SYNC_STATUS_RESET && ++retry <= max_retry) {
        printf("[NTP] Waiting... (%d/%d)\n", retry, max_retry);
        fflush(stdout);
        vTaskDelay(1000 / portTICK_PERIOD_MS);
    }
    if (retry > max_retry) {
        printf("[NTP] Time sync timeout!\n");
    } else {
        printf("[TIME_SYNC_OK] NTP time synchronized!\n");
    }
    fflush(stdout);
}

// --- UART / 시리얼 입력 ---
void uart_init_config(void) {
    const uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    uart_driver_install(UART_NUM, UART_BUF_SIZE, 0, 0, NULL, 0);
    uart_param_config(UART_NUM, &uart_config);
    printf("[UART] UART driver configured for input\n");
}

void serial_input_task(void *pvParameters) {
    uint8_t data[BUF_SIZE];

    printf("[SERIAL_TASK] Started with UART driver\n");

    while (1) {
        int len = uart_read_bytes(UART_NUM, data, BUF_SIZE - 1, 100 / portTICK_PERIOD_MS);
        if (len > 0) {
            data[len] = '\0';

            if (cmd_buf_len + (size_t)len >= CMD_BUF_SIZE) {
                cmd_buf_len = 0;
            }
            memcpy(cmd_buf + cmd_buf_len, data, (size_t)len);
            cmd_buf_len += (size_t)len;
            cmd_buf[cmd_buf_len] = '\0';

            // 줄 단위로 처리
            char *cur = cmd_buf;
            char *next;
            while ((next = strchr(cur, '\n')) != NULL) {
                *next = '\0';
                process_one_line(cur);
                cur = next + 1;
            }

            // 처리한 만큼 버퍼 앞으로 당기기
            size_t remain = (size_t)(cmd_buf + cmd_buf_len - cur);
            if (remain > 0 && cur > cmd_buf) {
                memmove(cmd_buf, cur, remain);
            }
            cmd_buf_len = remain;
            cmd_buf[cmd_buf_len] = '\0';
        }

        // 리부트 요청 처리
        if (reboot_requested) {
            printf("\n>>> [SYSTEM] REBOOTING <<<\n");
            fflush(stdout);
            vTaskDelay(200 / portTICK_PERIOD_MS);
            esp_restart();
        }

        vTaskDelay(10 / portTICK_PERIOD_MS);
    }
}

// --- 출력 함수들 ---
void print_system_info(void) {
    esp_chip_info_t chip_info;
    uint32_t flash_size;
    esp_chip_info(&chip_info);
    
    char chip_str[64];
    char flash_str[64];
    char features_str[64] = "";
    char mac_str[32];
    
    // Chip 정보 포맷팅
    snprintf(chip_str, sizeof(chip_str), "- Chip: %s, Cores: %d, Rev: v%d.%d", 
             CONFIG_IDF_TARGET, chip_info.cores, chip_info.revision / 100, chip_info.revision % 100);
             
    // Flash 정보 포맷팅
    if(esp_flash_get_size(NULL, &flash_size) == ESP_OK) {
        snprintf(flash_str, sizeof(flash_str), "- Flash: %" PRIu32 "MB, Min Heap: %" PRIu32 " bytes", 
                 flash_size / (1024 * 1024), esp_get_minimum_free_heap_size());
    } else {
        snprintf(flash_str, sizeof(flash_str), "- Flash: Unknown");
    }

    // 기능 정보 (Features) 구성
    if (chip_info.features & CHIP_FEATURE_WIFI_BGN) strcat(features_str, "WiFi/");
    if (chip_info.features & CHIP_FEATURE_BT) strcat(features_str, "BT/");
    if (chip_info.features & CHIP_FEATURE_BLE) strcat(features_str, "BLE/");
    if (chip_info.features & CHIP_FEATURE_IEEE802154) strcat(features_str, "802.15.4/");
    if (chip_info.features & CHIP_FEATURE_EMB_FLASH) strcat(features_str, "EmbFlash/");
    if (chip_info.features & CHIP_FEATURE_EMB_PSRAM) strcat(features_str, "EmbPSRAM/");
    
    // 마지막 슬래시 제거
    size_t len = strlen(features_str);
    if (len > 0) features_str[len - 1] = '\0';
    
    // MAC 주소 가져오기
    uint8_t mac[6];
    esp_efuse_mac_get_default(mac);
    snprintf(mac_str, sizeof(mac_str), "- MAC: %02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    // 현재 시간 가져오기
    time_t now;
    struct tm timeinfo;
    time(&now);
    
    setenv("TZ", "KST-9", 1);
    tzset();
    localtime_r(&now, &timeinfo);
    
    char time_str[64];
    strftime(time_str, sizeof(time_str), "- Time: %Y-%m-%d %H:%M:%S", &timeinfo);

    /* 
    ============================================
             ESP-Web-Monitor v3.0 (NTP)         
    --------------------------------------------
    - Chip: esp32s3, Cores: 2, Rev: v0.2         
    - Flash: 16MB, Min Heap: ... bytes     
    - Feat: WiFi/BLE/EmbPSRAM
    - MAC: 3C:0F:02:D0:25:14    
    - Location: Seoul, Korea                             
    - Time: 2026-02-06 14:39:15                             
    ============================================
    */
    printf("\n============================================\n");
    fflush(stdout);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    printf("         ESP-Web-Monitor v3.0 (NTP)         \n");
    fflush(stdout);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    printf("--------------------------------------------\n");
    fflush(stdout);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    printf("%-44s\n", chip_str);
    fflush(stdout);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    printf("%-44s\n", flash_str);
    fflush(stdout);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    printf("- Feat: %-36s\n", features_str);
    fflush(stdout);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    printf("%-44s\n", mac_str);
    fflush(stdout);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    printf("- Location: Seoul, Korea                    \n");
    fflush(stdout);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    printf("%-44s\n", time_str);
    fflush(stdout);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    printf("============================================\n");
    fflush(stdout);
    vTaskDelay(100 / portTICK_PERIOD_MS);
}

// --- 5가지 텍스트 애니메이션 함수들 ---

// 1. Loading Bar
void anim_loading_bar(void) {
    const int steps = 10;
    for (int i = 0; i <= steps; i++) {
        printf("[");
        for (int j = 0; j < steps; j++) {
            if (j < i) printf("=");
            else if (j == i) printf(">");
            else printf(" ");
        }
        printf("] %d%%\n", i * 10);
        fflush(stdout);
        vTaskDelay(200 / portTICK_PERIOD_MS);
    }
}

// 2. Typing Effect
void anim_typing(void) {
    const char *text = "NEXT UPDATE IN 3..2..1..";
    size_t len = strlen(text);
    char buf[32] = {0};
    
    for (size_t i = 1; i <= len; i++) {
        strncpy(buf, text, i);
        buf[i] = '\0';
        printf("%s_\n", buf);
        fflush(stdout);
        vTaskDelay(100 / portTICK_PERIOD_MS);
    }
}

// 3. Arrow Focus
void anim_arrow_focus(void) {
    const char *patterns[] = {
        ">>>      3      <<<",
        " >>      3      << ",
        "  >      3      <  ",
        "         3         ",
        ">>>      2      <<<",
        " >>      2      << ",
        "  >      2      <  ",
        "         2         ",
        ">>>      1      <<<",
        " >>      1      << ",
        "  >      1      <  ",
        "         1         ",
        "       Start!      "
    };
    int count = sizeof(patterns) / sizeof(patterns[0]);
    for(int i=0; i<count; i++) {
        printf("%s\n", patterns[i]);
        fflush(stdout);
        vTaskDelay(200 / portTICK_PERIOD_MS);
    }
}

// 4. Matrix Rain (Simple)
void anim_matrix_rain(void) {
    for (int i = 0; i < 15; i++) {
        for (int j = 0; j < 30; j++) {
            // 랜덤하게 0 또는 1 또는 공백 출력
            int r = rand() % 5;
            if (r == 0) printf("0");
            else if (r == 1) printf("1");
            else printf(" ");
        }
        printf("\n");
        fflush(stdout);
        vTaskDelay(150 / portTICK_PERIOD_MS);
    }
}

// 5. Wave Effect
void anim_wave(void) {
    const char *text = "LOADING...";
    int len = strlen(text);
    for(int i=0; i<15; i++) {
        for(int j=0; j<len; j++) {
            if (j == i % len) printf("[%c]", text[j]);
            else printf("%c", text[j]);
        }
        printf("\n");
        fflush(stdout);
        vTaskDelay(150 / portTICK_PERIOD_MS);
    }
}


void app_main(void) {
    // NVS 초기화 (WiFi에 필요)
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // UART 드라이버 초기화
    uart_init_config();

    // 별도 태스크로 시리얼 입력 처리 (메인 루프와 독립적)
    xTaskCreate(serial_input_task, "serial_input", 4096, NULL, 5, NULL);

    // WiFi STA 모드 초기화 및 연결
    wifi_init_sta();

    // WiFi 연결 대기 (최대 10초)
    printf("[WIFI] Waiting for connection...\n");
    fflush(stdout);
    EventBits_t bits = xEventGroupWaitBits(s_wifi_event_group,
            WIFI_CONNECTED_BIT, pdFALSE, pdFALSE, 10000 / portTICK_PERIOD_MS);
    if (bits & WIFI_CONNECTED_BIT) {
        printf("[WIFI] Connected successfully!\n");
    } else {
        printf("[WIFI] Connection timeout, continuing anyway...\n");
    }
    fflush(stdout);

    // NTP 시간 동기화
    initialize_sntp();
    wait_for_time_sync();

    static int anim_index = 0;

    // 메인 루프
    while(1) {
        // 1. 시스템 정보 출력 (박스 형태)
        print_system_info();
        
        // 2. 충분한 대기 시간 (박스와 애니메이션 분리)
        fflush(stdout);
        vTaskDelay(1000 / portTICK_PERIOD_MS); 
        
        // 3. 애니메이션 시작 알림
        // printf("\n--- Animation Style %d ---\n", anim_index + 1);
        // fflush(stdout);
        
        // 5가지 애니메이션 순차 실행 (매 루프마다 변경)
        switch(anim_index) {
            case 0: anim_loading_bar(); break;
            case 1: anim_typing(); break;
            case 2: anim_arrow_focus(); break;
            case 3: anim_matrix_rain(); break;
            case 4: anim_wave(); break;
        }
        
        anim_index = (anim_index + 1) % 5;
        
        // 4. 다음 루프 전 대기
        vTaskDelay(2000 / portTICK_PERIOD_MS);
    }
}
