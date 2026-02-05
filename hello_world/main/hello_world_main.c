/*
 * SPDX-FileCopyrightText: 2010-2022 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: CC0-1.0
 */

#include <stdio.h>
#include <inttypes.h>
#include <string.h>
#include <time.h>
#include <sys/time.h>
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_system.h"

void print_system_info(void) {
    printf("ESP-Web-Monitor by Jinho Jung! \n");

    /* Print chip information */
    esp_chip_info_t chip_info;
    uint32_t flash_size;
    esp_chip_info(&chip_info);
    printf("This is %s chip with %d CPU core(s), %s%s%s%s, ",
           CONFIG_IDF_TARGET,
           chip_info.cores,
           (chip_info.features & CHIP_FEATURE_WIFI_BGN) ? "WiFi/" : "",
           (chip_info.features & CHIP_FEATURE_BT) ? "BT" : "",
           (chip_info.features & CHIP_FEATURE_BLE) ? "BLE" : "",
           (chip_info.features & CHIP_FEATURE_IEEE802154) ? ", 802.15.4 (Zigbee/Thread)" : "");

    unsigned major_rev = chip_info.revision / 100;
    unsigned minor_rev = chip_info.revision % 100;
    printf("silicon revision v%d.%d, ", major_rev, minor_rev);
    if(esp_flash_get_size(NULL, &flash_size) != ESP_OK) {
        printf("Get flash size failed");
        return;
    }

    printf("%" PRIu32 "MB %s flash\n", flash_size / (uint32_t)(1024 * 1024),
           (chip_info.features & CHIP_FEATURE_EMB_FLASH) ? "embedded" : "external");

    printf("Minimum free heap size: %" PRIu32 " bytes\n", esp_get_minimum_free_heap_size());
}

void print_big_number(int num) {
    const char *ascii_art[6][5] = {
        // 0
        {" ___  ", "|   | ", "| | | ", "|   | ", " ---  "},
        // 1
        {"  _   ", " / |  ", "  | ", "  |  ", " _|_  "},
        // 2
        {" ___  ", "|_  | ", "  / / ", " / /_ ", "|____| "},
        // 3
        {" ___  ", "|_  | ", "  _| | ", " |_  | ", " ___| "},
        // 4
        {"   _   ", "  | |  ", " _| |_ ", "|_   _| ", "  |_|  "},
        // 5
        {" _____ ", "|  ___| ", "| |___  ", "|___  | ", " ____| "}
    };
    
    for (int line = 0; line < 5; line++) {
        printf("%s\n", ascii_art[num][line]);
        vTaskDelay(100 / portTICK_PERIOD_MS); // 각 줄마다 0.1초 지연
    }
}

void print_current_time_and_location(void)
{
    time_t now;
    struct tm timeinfo;
    time(&now);
    
    // 한국 시간대 설정 (KST = UTC+9)
    setenv("TZ", "KST-9", 1);
    tzset();
    localtime_r(&now, &timeinfo);

    char date_buf[64];
    char time_buf[32];
    
    strftime(date_buf, sizeof(date_buf), "%Y-%m-%d (%A)", &timeinfo);
    strftime(time_buf, sizeof(time_buf), "%H:%M:%S", &timeinfo);
    
    printf("\n");
    printf("+--------------------------------------------+\n");
    printf("|          CURRENT TIME & LOCATION          |\n");
    printf("+--------------------------------------------+\n");
    
    // Date 줄: "|  Date: " = 9자, date_buf, 공백, "|" = 1자
    // 전체 = 44자이므로 내용 부분 = 44 - 2 = 42자
    printf("|  Date: %-32s |\n", date_buf);
    
    // Time 줄: "|  Time: " = 9자, time_buf, 공백, "|" = 1자  
    printf("|  Time: %-32s |\n", time_buf);
    
    printf("+--------------------------------------------+\n");
    printf("|  Location: Seoul, South Korea             |\n");
    printf("|  Timezone: KST (UTC+9)                    |\n");
    printf("+--------------------------------------------+\n");
    printf("\n");
}

void app_main(void)
{
    while(1) {
        print_system_info();
        printf("\n");
        
        // ASCII 카운트다운
        for (int i = 5; i >= 1; i--) {
            printf("\n");
            print_big_number(i); // 여기서 이미 약 0.5초 소요됨 (5줄 * 0.1초)
            printf("\n");
            vTaskDelay(500 / portTICK_PERIOD_MS); // 나머지 0.5초 대기하여 총 약 1초 간격 유지
        }
        
        // 현재 시간과 위치 표시
        print_current_time_and_location();
        
        printf("\n=== Refreshing... ===\n\n");
        vTaskDelay(3000 / portTICK_PERIOD_MS);
    }
}
