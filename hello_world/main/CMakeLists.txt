idf_component_register(SRCS "hello_world_main.c"
                       REQUIRES spi_flash esp_driver_uart esp_system
                                esp_wifi esp_netif esp_event nvs_flash lwip
                       INCLUDE_DIRS "")
