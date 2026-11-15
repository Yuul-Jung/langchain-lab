"""명세 1 질문 생성용 낱말 목록(지어낸 값 없음, 일반 지식). 규칙 파일(parts_graph·ontology 등)을 보지 않고 작성.

D 묶음별 항목: ko 한글 이름 · v 표기 변형(B5) · en 영문 용어(B4) · pn 실제 부품 이름 예(A2·A4) · libs 정답 라이브러리(카탈로그 구조, KiCad 디렉터리 이름).
조건 풀(C): v 전압 · p 패키지 · o 기타(채널·전류) · i 인터페이스.
"""
from __future__ import annotations

D_ITEMS = {
    "power": [
        dict(ko="저전압 강하 레귤레이터", v=["엘디오", "엘디오 레귤레이터", "LDO레귤레이터"], en="LDO regulator", pn=["LM317", "AMS1117", "LM1117", "MIC5205", "LD1117"], libs=["Regulator_Linear"]),
        dict(ko="스위칭 전압 변환기", v=["벅컨버터", "강압 컨버터", "스텝다운 컨버터"], en="buck converter", pn=["LM2596", "MP1584", "TPS5430", "LM2576"], libs=["Regulator_Switching", "Converter_DCDC"]),
        dict(ko="승압 컨버터", v=["부스트컨버터", "승압용 칩", "업컨버터"], en="boost converter", pn=["MT3608", "TPS61200", "LM2577"], libs=["Regulator_Switching", "Converter_DCDC"]),
        dict(ko="전압 기준 소자", v=["전압레퍼런스", "기준전압 IC", "레퍼런스 전압"], en="voltage reference", pn=["TL431", "LM4040", "REF3030", "LM336"], libs=["Reference_Voltage"]),
        dict(ko="배터리 충전 관리 칩", v=["배터리충전 IC", "충전IC", "리튬 충전칩"], en="battery charger IC", pn=["TP4056", "MCP73831", "BQ24074"], libs=["Battery_Management"]),
        dict(ko="전원 감시 리셋 칩", v=["리셋 IC", "전원감시", "슈퍼바이저"], en="power supervisor", pn=["TPS3823", "MAX811", "STM6315"], libs=["Power_Supervisor"]),
        dict(ko="전하 펌프", v=["차지펌프", "차지 펌프 IC", "전압 인버터 칩"], en="charge pump", pn=["ICL7660", "MAX1044", "TPS60403"], libs=["Regulator_SwitchedCapacitor"]),
        dict(ko="절연형 직류 변환 모듈", v=["절연 디씨디씨", "아이솔레이티드 DCDC", "절연전원모듈"], en="isolated DC-DC module", pn=["TMA0505S", "NME0505", "R1SX"], libs=["Converter_DCDC_Isolated"]),
        dict(ko="교류 직류 전원 변환기", v=["AC DC 컨버터", "에이씨디씨", "AC-DC 전원 모듈"], en="AC-DC converter", pn=["HLK-PM01", "IRM-03-5", "TMLM"], libs=["Converter_ACDC"]),
        dict(ko="과전압 보호 소자", v=["서지 보호", "티브이에스 다이오드", "ESD 보호 소자"], en="surge protection device", pn=["SMBJ5.0A", "PRTR5V0U2X", "TPD4E05"], libs=["Power_Protection"]),
    ],
    "analog": [
        dict(ko="연산 증폭기", v=["오피앰프", "OP앰프", "연산증폭기"], en="op-amp", pn=["LM358", "TL072", "LM324", "OPA2134", "MCP6002"], libs=["Amplifier_Operational"]),
        dict(ko="계측용 증폭기", v=["인스트루멘테이션 앰프", "계측앰프", "인앰프"], en="instrumentation amplifier", pn=["INA128", "AD620", "INA333"], libs=["Amplifier_Instrumentation"]),
        dict(ko="오디오 출력 증폭기", v=["오디오앰프", "스피커 앰프", "클래스D 앰프"], en="audio power amplifier", pn=["LM386", "PAM8403", "TDA2030"], libs=["Amplifier_Audio"]),
        dict(ko="전압 비교기", v=["콤퍼레이터", "비교기 IC", "컴퍼레이터"], en="comparator", pn=["LM393", "LM311", "TLV3201"], libs=["Comparator"]),
        dict(ko="아날로그 디지털 변환기", v=["에이디씨", "ADC칩", "AD 변환기"], en="ADC", pn=["ADS1115", "MCP3008", "ADS1256"], libs=["Analog_ADC"]),
        dict(ko="디지털 아날로그 변환기", v=["디에이씨", "DAC칩", "DA 변환기"], en="DAC", pn=["MCP4725", "DAC8552", "AD5693"], libs=["Analog_DAC"]),
        dict(ko="아날로그 멀티플렉서", v=["아날로그스위치", "아날로그 먹스", "멀티플렉서 IC"], en="analog switch", pn=["CD4066", "74HC4051", "ADG704"], libs=["Analog_Switch"]),
        dict(ko="디지털 가변 저항", v=["디지털 포텐쇼미터", "디지팟", "가변저항 IC"], en="digital potentiometer", pn=["MCP4131", "AD5206", "X9C103"], libs=["Potentiometer_Digital"]),
        dict(ko="전류 감지 증폭기", v=["전류센스앰프", "션트 앰프", "하이사이드 전류 감지"], en="current sense amplifier", pn=["INA219", "INA180", "MAX9918"], libs=["Amplifier_Current"]),
        dict(ko="능동 필터 칩", v=["필터 IC", "스위치드 커패시터 필터", "필터칩"], en="active filter IC", pn=["MAX7400", "LTC1060", "MF10"], libs=["Filter"]),
    ],
    "logic": [
        dict(ko="논리 게이트", v=["로직게이트", "게이트 IC", "논리소자"], en="logic gate", pn=["74HC00", "74HC08", "CD4011", "SN74LVC1G08"], libs=["74xx", "74xGxx", "4xxx", "74xx_IEEE", "4xxx_IEEE"]),
        dict(ko="전압 레벨 변환기", v=["레벨시프터", "레벨 쉬프터", "전압레벨변환"], en="level shifter", pn=["TXB0104", "74LVC245", "PCA9306", "BSS138 모듈"], libs=["Logic_LevelTranslator"]),
        dict(ko="디지털 카운터", v=["카운터 IC", "분주기 칩", "이진 카운터"], en="counter IC", pn=["74HC161", "CD4017", "CD4040", "74HC393"], libs=["74xx", "74xx_IEEE", "4xxx", "4xxx_IEEE"]),
        dict(ko="플립플롭", v=["플립 플롭", "래치 IC", "D 플립플롭"], en="flip-flop", pn=["74HC74", "74HC573", "CD4013"], libs=["74xx", "74xGxx", "74xx_IEEE", "4xxx", "4xxx_IEEE"]),
        dict(ko="시프트 레지스터", v=["쉬프트 레지스터", "시프트레지스터 IC", "직병렬 변환기"], en="shift register", pn=["74HC595", "74HC165", "CD4094"], libs=["74xx", "74xx_IEEE", "4xxx", "4xxx_IEEE"]),
        dict(ko="프로그래머블 논리 소자", v=["프로그래머블 로직", "피엘디", "CPLD"], en="programmable logic device", pn=["ATF1504", "XC9572", "GAL16V8"], libs=["Logic_Programmable", "CPLD_Altera", "CPLD_Xilinx", "CPLD_Microchip", "CPLD_Renesas"]),
        dict(ko="현장 프로그래머블 게이트 어레이", v=["에프피지에이", "FPGA칩", "FPGA"], en="FPGA", pn=["XC6SLX9", "ICE40", "EP4CE6"], libs=["FPGA_Lattice", "FPGA_Xilinx", "FPGA_Xilinx_Artix7", "FPGA_Xilinx_Kintex7", "FPGA_Xilinx_Spartan6", "FPGA_Xilinx_Virtex5", "FPGA_Xilinx_Virtex6", "FPGA_Xilinx_Virtex7", "FPGA_Altera_MAX10", "FPGA_Microsemi", "FPGA_Efinix_Trion", "FPGA_CologneChip_GateMate"]),
        dict(ko="버퍼 드라이버", v=["버퍼 IC", "라인 버퍼", "논리 버퍼"], en="buffer driver", pn=["74HC244", "74HC541", "74LVC1G17"], libs=["74xx", "74xGxx", "74xx_IEEE", "Buffer"]),
    ],
    "mcu_mem": [
        dict(ko="에이브이알 마이크로컨트롤러", v=["아트메가", "AVR 마이컴", "아두이노용 칩"], en="AVR microcontroller", pn=["ATmega328P", "ATtiny85", "ATmega2560"], libs=["MCU_Microchip_ATmega", "MCU_Microchip_ATtiny", "MCU_Microchip_AVR", "MCU_Microchip_AVR_Dx"]),
        dict(ko="ARM 코어텍스 마이크로컨트롤러", v=["STM32 마이컴", "스엠 32", "ARM 마이컴"], en="STM32 microcontroller", pn=["STM32F103", "STM32G031", "STM32L432"], libs=[l for l in ("MCU_ST_STM32C0", "MCU_ST_STM32F0", "MCU_ST_STM32F1", "MCU_ST_STM32F2", "MCU_ST_STM32F3", "MCU_ST_STM32F4", "MCU_ST_STM32F7", "MCU_ST_STM32G0", "MCU_ST_STM32G4", "MCU_ST_STM32H5", "MCU_ST_STM32H7", "MCU_ST_STM32L0", "MCU_ST_STM32L1", "MCU_ST_STM32L4", "MCU_ST_STM32L5", "MCU_ST_STM32U0", "MCU_ST_STM32U5", "MCU_ST_STM32WB", "MCU_ST_STM32WL", "MCU_ST_STM8")]),
        dict(ko="피아이씨 마이컴", v=["PIC 마이크로컨트롤러", "피씨 마이컴", "PIC 칩"], en="PIC microcontroller", pn=["PIC16F877A", "PIC18F4550", "PIC12F675"], libs=["MCU_Microchip_PIC10", "MCU_Microchip_PIC12", "MCU_Microchip_PIC16", "MCU_Microchip_PIC18", "MCU_Microchip_PIC24", "MCU_Microchip_PIC32"]),
        dict(ko="초저전력 16비트 마이컴", v=["엠에스피 430", "MSP430 칩", "저전력 마이크로컨트롤러"], en="MSP430 microcontroller", pn=["MSP430G2553", "MSP430F5529", "MSP430FR2433"], libs=["MCU_Texas_MSP430", "MCU_Texas"]),
        dict(ko="직렬 이이피롬", v=["EEPROM", "이이프롬", "I2C 메모리"], en="serial EEPROM", pn=["24C02", "AT24C256", "93C46"], libs=["Memory_EEPROM"]),
        dict(ko="플래시 메모리 칩", v=["플래시메모리", "낸드 노어 플래시", "SPI 플래시"], en="flash memory", pn=["W25Q64", "SST25VF016", "MX25L6406"], libs=["Memory_Flash"]),
        dict(ko="정적 램", v=["에스램", "SRAM", "스태틱램"], en="SRAM", pn=["IS62WV", "CY62256", "23LC1024"], libs=["Memory_RAM", "Memory_NVRAM"]),
        dict(ko="실시간 시계 칩", v=["알티씨", "RTC IC", "시계 IC"], en="real-time clock", pn=["DS3231", "PCF8563", "DS1307"], libs=["Timer_RTC"]),
        dict(ko="와이파이 내장 마이컴", v=["ESP 칩", "이에스피", "와이파이 마이컴"], en="Wi-Fi microcontroller", pn=["ESP32-WROOM", "ESP8266", "ESP32-C3"], libs=["MCU_Espressif", "MCU_Module", "RF_Module"]),
    ],
    "comm_rf": [
        dict(ko="유아트 직렬 통신 칩", v=["RS232 변환", "시리얼 칩", "UART 브리지"], en="UART transceiver", pn=["MAX232", "FT232RL", "CH340", "SP3485"], libs=["Interface_UART", "Interface_USB"]),
        dict(ko="캔 버스 송수신기", v=["CAN 트랜시버", "캔통신 IC", "캔 버스 칩"], en="CAN transceiver", pn=["TJA1050", "MCP2551", "SN65HVD230", "MCP2515"], libs=["Interface_CAN_LIN"]),
        dict(ko="이더넷 물리 계층 칩", v=["이더넷 PHY", "랜 칩", "이더넷컨트롤러"], en="Ethernet PHY", pn=["W5500", "ENC28J60", "LAN8720"], libs=["Interface_Ethernet"]),
        dict(ko="USB 직렬 변환 칩", v=["USB 시리얼", "유에스비 브리지", "USB UART 칩"], en="USB-to-serial bridge", pn=["CP2102", "FT232", "CH340G"], libs=["Interface_USB", "Interface_UART"]),
        dict(ko="블루투스 모듈", v=["블루투스 칩", "BLE 모듈", "비엘이"], en="Bluetooth module", pn=["HC-05", "nRF52832", "HM-10"], libs=["RF_Bluetooth", "RF_Module", "MCU_Nordic"]),
        dict(ko="위성 위치 수신기", v=["지피에스 모듈", "GPS 칩", "GNSS 모듈"], en="GPS receiver", pn=["NEO-6M", "L80", "MAX-M8Q"], libs=["RF_GPS", "RF_Module"]),
        dict(ko="근거리 무선 태그 칩", v=["엔에프씨", "NFC 리더", "RFID 리더 칩"], en="NFC reader", pn=["PN532", "MFRC522", "ST25R3916"], libs=["RF_NFC", "RF_RFID", "RF_Module"]),
        dict(ko="고주파 증폭기", v=["RF 앰프", "무선 증폭 칩", "알에프 증폭기"], en="RF amplifier", pn=["SKY65116", "BGA2803", "MGA-30189"], libs=["RF_Amplifier"]),
        dict(ko="지그비 무선 칩", v=["ZigBee 모듈", "지그비모듈", "802.15.4 칩"], en="ZigBee module", pn=["CC2530", "XBee", "EM357"], libs=["RF_ZigBee", "RF_Module"]),
    ],
    "sensor": [
        dict(ko="온도 측정 소자", v=["온도센서", "온도 센서 IC", "써미스터 칩"], en="temperature sensor", pn=["DS18B20", "LM35", "TMP36", "MCP9808"], libs=["Sensor_Temperature"]),
        dict(ko="가속도 자이로 센서", v=["가속도센서", "IMU 칩", "관성 센서"], en="accelerometer", pn=["MPU6050", "ADXL345", "LIS3DH"], libs=["Sensor_Motion"]),
        dict(ko="기압 측정 칩", v=["압력센서", "대기압 센서", "기압계 IC"], en="pressure sensor", pn=["BMP280", "MPX5700", "MS5611"], libs=["Sensor_Pressure"]),
        dict(ko="습도 감지 칩", v=["습도센서", "온습도 센서", "휴미디티 센서"], en="humidity sensor", pn=["DHT22", "SHT31", "HDC1080"], libs=["Sensor_Humidity"]),
        dict(ko="자기장 감지 소자", v=["홀센서", "홀 효과 센서", "자석 센서"], en="Hall effect sensor", pn=["A3144", "US1881", "DRV5053"], libs=["Sensor_Magnetic"]),
        dict(ko="거리 측정 센서", v=["근접센서", "거리센서", "적외선 근접 센서"], en="proximity sensor", pn=["VL53L0X", "GP2Y0A21", "VCNL4010"], libs=["Sensor_Distance", "Sensor_Proximity", "Sensor_Optical"]),
        dict(ko="전류 측정 센서", v=["전류센서", "전류 검출 IC", "홀 전류 센서"], en="current sensor", pn=["ACS712", "ACS758", "INA226"], libs=["Sensor_Current", "Sensor_Energy"]),
        dict(ko="빛 감지 소자", v=["조도센서", "광센서", "포토 센서"], en="ambient light sensor", pn=["BH1750", "TSL2561", "APDS-9960"], libs=["Sensor_Optical"]),
        dict(ko="가스 감지 센서", v=["가스센서", "공기질 센서", "유해가스 감지"], en="gas sensor", pn=["MQ-2", "CCS811", "BME680"], libs=["Sensor_Gas"]),
        dict(ko="정전식 터치 칩", v=["터치센서", "터치 감지 IC", "정전용량 터치"], en="capacitive touch sensor", pn=["TTP223", "MPR121", "CAP1188"], libs=["Sensor_Touch"]),
    ],
    "drive_em": [
        dict(ko="직류 모터 구동 칩", v=["모터드라이버", "모터 드라이브 IC", "H브리지 칩"], en="motor driver", pn=["L298N", "DRV8833", "TB6612", "A4988"], libs=["Driver_Motor"]),
        dict(ko="전자기계식 릴레이", v=["릴레이", "릴레이 부품", "계전기"], en="electromechanical relay", pn=["SRD-05VDC", "G5V-1", "HFD2"], libs=["Relay"]),
        dict(ko="반도체 릴레이", v=["솔리드스테이트 릴레이", "SSR", "무접점 릴레이"], en="solid-state relay", pn=["G3MB-202P", "TLP3543", "AQY210"], libs=["Relay_SolidState"]),
        dict(ko="모스펫 게이트 구동 칩", v=["게이트드라이버", "FET 드라이버 IC", "게이트 드라이브"], en="MOSFET gate driver", pn=["IR2110", "TC4420", "UCC27524"], libs=["Driver_FET"]),
        dict(ko="발광 다이오드 구동 칩", v=["LED드라이버", "엘이디 드라이버", "정전류 LED 칩"], en="LED driver", pn=["TLC5940", "PCA9685", "AP3602"], libs=["Driver_LED"]),
        dict(ko="표시 장치 구동 칩", v=["디스플레이 드라이버", "세그먼트 드라이버", "디스플레이 구동 IC"], en="display driver", pn=["MAX7219", "TM1637", "HT16K33"], libs=["Driver_Display", "Display_Character", "Display_Graphic"]),
        dict(ko="양방향 사이리스터", v=["트라이악", "트라이액 소자", "교류 스위칭 소자"], en="triac", pn=["BT136", "BTA16", "MOC3021"], libs=["Triac_Thyristor"]),
        dict(ko="달링턴 트랜지스터 배열", v=["트랜지스터 어레이", "달링턴 어레이", "ULN 계열"], en="Darlington array", pn=["ULN2003", "ULN2803", "TD62003"], libs=["Transistor_Array"]),
    ],
    "discrete": [
        dict(ko="양극성 접합 트랜지스터", v=["바이폴라 트랜지스터", "BJT", "범용 트랜지스터"], en="bipolar transistor", pn=["2N2222", "2N3904", "BC547", "TIP120"], libs=["Transistor_BJT"]),
        dict(ko="전계효과 트랜지스터", v=["모스펫", "MOSFET", "파워 모스펫"], en="MOSFET", pn=["IRF540", "2N7000", "AO3400", "IRLZ44N"], libs=["Transistor_FET", "Transistor_FET_Other"]),
        dict(ko="범용 정류 다이오드", v=["정류다이오드", "스위칭 다이오드", "다이오드"], en="rectifier diode", pn=["1N4148", "1N4007", "1N5819"], libs=["Diode"]),
        dict(ko="브리지 정류기", v=["브릿지 다이오드", "정류 브리지", "전파 정류 소자"], en="bridge rectifier", pn=["DB107", "KBP307", "MB6S"], libs=["Diode_Bridge"]),
        dict(ko="절연 게이트 바이폴라 소자", v=["아이지비티", "IGBT", "전력 모듈"], en="IGBT", pn=["IRG4PC40", "FGH40N60", "GT30J"], libs=["Transistor_IGBT", "Transistor_Power_Module"]),
        dict(ko="발광 다이오드", v=["엘이디", "LED", "표시등 LED"], en="light-emitting diode", pn=["WS2812B", "L-53", "SK6812"], libs=["LED"]),
        dict(ko="정전압 다이오드", v=["제너다이오드", "제너", "전압 클램프 소자"], en="Zener diode", pn=["1N4733", "BZX84", "BZX55"], libs=["Diode"]),
        dict(ko="쇼트키 다이오드", v=["쇼트키", "저손실 다이오드", "슈트키 다이오드"], en="Schottky diode", pn=["SS14", "BAT54", "1N5822"], libs=["Diode"]),
    ],
    "passive_conn": [
        dict(ko="핀 헤더 커넥터", v=["핀헤더", "헤더 핀", "2.54mm 커넥터"], en="pin header", pn=["PH-2.54", "Molex KK", "JST XH"], libs=["Connector", "Connector_Generic", "Connector_Generic_MountingPin", "Connector_Generic_Shielded"]),
        dict(ko="오디오 잭", v=["3.5mm 잭", "헤드폰 잭", "오디오커넥터"], en="audio jack", pn=["PJ-307", "SJ1-3523", "PJ-320"], libs=["Connector_Audio"]),
        dict(ko="전원 변압기", v=["트랜스", "트랜스포머", "펄스 트랜스"], en="transformer", pn=["EI-30", "HX1188", "T1-1"], libs=["Transformer"]),
        dict(ko="택트 스위치", v=["푸시버튼", "누름 스위치", "택트스위치"], en="tactile switch", pn=["B3F", "SKQG", "TS-1187"], libs=["Switch"]),
        dict(ko="슬라이드 스위치", v=["토글스위치", "딥스위치", "슬라이드스위치"], en="slide switch", pn=["SS-12D00", "MTS-102", "DS-04"], libs=["Switch"]),
        dict(ko="저항 소자", v=["칩저항", "저항기", "저항"], en="resistor", pn=["RC0603", "CFR-25JB", "ERJ-3"], libs=["Device"]),
        dict(ko="전해 콘덴서", v=["전해커패시터", "알루미늄 커패시터", "콘덴서"], en="electrolytic capacitor", pn=["UVR1H", "EEU-FR", "UHE"], libs=["Device"]),
        dict(ko="점퍼 핀", v=["점퍼", "쇼팅 점퍼", "점퍼선 커넥터"], en="jumper", pn=["JP1", "SJ-1", "TJ-1"], libs=["Jumper", "Connector", "Connector_Generic"]),
    ],
    "module": [
        dict(ko="문자 표시 액정 모듈", v=["문자 LCD", "캐릭터 LCD", "16x2 LCD"], en="character LCD module", pn=["HD44780", "LCD1602", "ST7066"], libs=["Display_Character"]),
        dict(ko="그래픽 표시 장치", v=["OLED 디스플레이", "그래픽 LCD", "그래픽 액정"], en="graphic display", pn=["SSD1306", "ST7735", "ILI9341"], libs=["Display_Graphic", "Display_Character"]),
        dict(ko="수정 발진 모듈", v=["크리스탈 오실레이터", "클록 모듈", "오실레이터"], en="crystal oscillator", pn=["SG-8002", "ASE-8MHz", "ECS-100"], libs=["Oscillator"]),
        dict(ko="디지털 신호 절연기", v=["디지털 아이솔레이터", "절연 IC", "신호 절연 칩"], en="digital isolator", pn=["ADuM1201", "ISO7721", "Si8621"], libs=["Isolator", "Isolator_Analog"]),
        dict(ko="포토커플러", v=["옵토커플러", "광절연기", "포토 커플러"], en="optocoupler", pn=["PC817", "4N35", "TLP521"], libs=["Isolator"]),
        dict(ko="오디오 코덱 칩", v=["오디오 IC", "사운드 코덱", "오디오 인터페이스 칩"], en="audio codec", pn=["WM8731", "PCM5102", "TLV320AIC3104"], libs=["Audio"]),
        dict(ko="영상 신호 칩", v=["비디오 IC", "HDMI 변환", "영상 처리 칩"], en="video IC", pn=["TFP401", "ADV7180", "TPD12S016"], libs=["Video", "Interface_HDMI", "Amplifier_Video"]),
        dict(ko="서보 모터", v=["서보모터", "미니 서보", "스테퍼 모터"], en="servo motor", pn=["SG90", "MG996R", "28BYJ-48"], libs=["Motor"]),
    ],
    "other_mixed": [
        dict(ko="타이머 칩", v=["555 타이머", "타이머IC", "오오오 타이머"], en="timer IC", pn=["NE555", "LM555", "TLC555", "NE556"], libs=["Timer"]),
        dict(ko="위상 고정 루프 칩", v=["피엘엘", "PLL 칩", "주파수 합성기"], en="PLL", pn=["CD4046", "ADF4351", "SI5351"], libs=["Timer_PLL"]),
        dict(ko="보안 인증 칩", v=["시큐리티 칩", "암호화 칩", "인증 IC"], en="secure element", pn=["ATECC608", "DS2432", "SE050"], libs=["Security", "Memory_UniqueID"]),
        dict(nocond=True, ko="진공관", v=["진공 튜브", "프리앰프용 진공관", "12AX7"], en="vacuum tube", pn=["12AX7", "EL34", "6L6"], libs=["Valve"]),
        dict(nocond=True, ko="광섬유 송수신기", v=["광트랜시버", "파이버 옵틱 모듈", "광통신 모듈"], en="fiber optic transceiver", pn=["HFBR-1521", "TOSLINK", "SFP"], libs=["Fiber_Optic", "Interface_Optical"]),
        dict(ko="자석으로 동작하는 스위치", v=["리드 스위치", "자석 스위치", "리드스위치"], en="reed switch", pn=["MKA-14103", "RI-80", "KSK-1A"], libs=["Switch", "Relay", "Sensor_Magnetic"]),
        dict(ko="디지털 신호 처리기", v=["디에스피", "DSP 칩", "신호처리 프로세서"], en="DSP", pn=["TMS320", "dsPIC33", "ADSP-2181"], libs=["DSP_Microchip_DSPIC33", "DSP_AnalogDevices", "DSP_Texas", "DSP_Freescale", "DSP_Motorola"]),
    ],
}

COND = {  # 조건 풀(C1~C3 에서 서로 다른 종류를 고른다). 각 항목은 수식어 구.
    "v": ["3.3V 입력", "5V 동작", "12V 전원", "1.8V 저전압", "24V 입력", "2.5V 이하 동작"],
    "p": ["SOT-23 패키지", "SOIC-8 패키지", "QFN 소형 패키지", "DIP 패키지", "표면 실장형", "TSSOP 패키지"],
    "o": ["2채널", "4채널", "저전력", "저잡음", "고속", "1A급"],
    "i": ["I2C 인터페이스", "SPI 인터페이스", "UART 지원", "USB 연결", "아날로그 출력", "디지털 출력"],
}

# E 하위 종류별 줄기. E4 는 (제품, 측면) 조합으로 90개 이상을 만든다.
E_STEMS = {
    "E1": ["무선 충전기 추천", "와이파이 공유기 순위", "로봇청소기 비교", "스마트워치 가격", "전기밥솥 인기 모델", "블루투스 이어폰 후기", "전동 킥보드 안전", "노트북 어댑터 호환", "공기청정기 필터 교체 주기", "에어프라이어 용량 고르기", "무선 마우스 배터리 수명", "전기면도기 비교", "태블릿 거치대 추천", "보조배터리 용량 선택", "TV 스피커 사운드바 추천", "전자레인지 고르는 법", "게이밍 키보드 순위", "스마트 전구 설정", "드론 입문용 추천", "차량용 블랙박스 비교", "스마트 도어락 후기", "무선 청소기 흡입력", "전자책 리더기 선택", "휴대용 선풍기 추천", "스마트 스피커 비교"],
    "E2": ["주말 등산 코스 추천", "라면 맛있게 끓이는 법", "제주도 3박 4일 일정", "봄에 볼 만한 영화", "김치찌개 레시피", "초보 러닝 훈련 계획", "독서 모임 운영 방법", "반려견 산책 시간", "캠핑 장비 체크리스트", "커피 원두 보관법", "서울 근교 당일 여행지", "수면 습관 개선", "집에서 하는 홈트레이닝", "한강 자전거 코스", "생일 선물 아이디어", "베란다 화분 키우기", "기타 코드 쉽게 외우기", "겨울 스키장 추천", "맥주 종류별 특징", "수채화 처음 배우기", "텃밭 상추 키우기", "혼자 떠나는 여행 팁", "집들이 메뉴 구성", "러닝화 고르는 기준", "보드게임 입문 추천"],
    "E3": ["릴레이 달리기 작전", "닌텐도 스위치 게임 추천", "야구 배터리 호흡", "감자칩 맛있는 브랜드", "카지노 칩 가치", "트랜스포머 영화 순서", "램 한 마리 가격", "코일 파마 비용", "버스 노선 환승", "센서 있는 스마트폰 카메라 셀카", "다이오드 가수 노래", "플래시 촬영 팁", "저항 운동 루틴", "모터쇼 일정", "스위치 켜는 습관 절약", "퓨즈 터진 듯한 분노 조절", "커넥터 사업 인맥 쌓기", "컨트롤러 게임패드 추천", "게이트 볼 규칙", "필터 커피 내리는 법", "램프 켜는 마술 공연", "전선 줄넘기 대회 규칙", "인덕터라는 이름의 밴드", "릴레이션십 상담 비용", "쇼트 컷 머리 관리"],
    "E5": ["파이썬 리스트 정렬 방법", "세금 신고 마감일", "오늘 서울 날씨", "영어 면접 자기소개", "엑셀 함수 합계", "이력서 쓰는 법", "도서관 대출 연장", "주식 투자 기초", "건강보험 자격 확인", "회의록 작성 요령", "한글 맞춤법 헷갈리는 말", "자전거 보험 가입", "전월세 계약 주의점", "운전면허 갱신 절차", "발표 자료 디자인 팁", "학자금 대출 상환", "깃 브랜치 합치기", "연말정산 공제 항목", "이사 체크리스트", "휴대폰 요금제 비교", "자기소개서 항목 구성", "부동산 등기부 보는 법", "스프레드시트 중복 제거", "국민연금 수령 시기", "정규식 이메일 검사"],
}
E4_PRODUCTS = ["에어컨", "냉장고", "세탁기", "전기차 충전기", "스마트폰 배터리", "태양광 패널", "LED 조명", "전기 보일러", "인덕션", "정수기", "공기청정기", "전기자전거", "UPS 무정전 전원", "자동차 시동 배터리", "형광등 안정기", "전기 히터", "식기세척기", "벽걸이 TV", "전동 공구", "가정용 누전 차단기"]
E4_ASPECTS = ["설치 비용", "고장 증상", "수리 센터 위치", "전기 요금", "교체 시기", "사용 후기"]

A5_TOPICS = ["핀 배치", "절대 최대 정격", "권장 동작 조건", "응용 회로 예시", "패키지 치수", "전기적 특성 표", "타이밍 다이어그램", "레지스터 맵", "열 저항 값", "주문 정보 표"]
