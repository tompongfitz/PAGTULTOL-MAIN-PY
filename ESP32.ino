#include <SPI.h>
#include <LoRa.h>
#include <TFT_eSPI.h>

#define HSPI_MISO   12
#define HSPI_MOSI   13
#define HSPI_SCLK   14
#define HSPI_SS     15
#define LORA_RST    26
#define LORA_DIO0   27

#define RX_LED_PIN    22  
#define BUZZER_PIN    21  
#define TFT_BL        16  
#define POWER_BTN_PIN 0   

SPIClass * hspi = NULL;
TFT_eSPI tft = TFT_eSPI();

bool isSystemOn = true;
unsigned long pressStartTime = 0;
bool isPressing = false;
bool hasToggled = false;

#define MED_BG      0x0000 
#define MED_GRID    0x0040 
#define MED_TEXT    0xFFFF 
#define MED_ALERT   0xF800 
#define MED_OK      0x07E0 
#define MED_ACCENT  0x07FF 

void updateStatus(String status, uint16_t color) {
  tft.fillRect(0, 301, 480, 19, MED_BG);
  tft.setTextColor(color, MED_BG);
  tft.setTextSize(1);
  tft.setCursor(10, 305);
  tft.print(status);
}

void triggerBuzzer() {
  for (int i = 0; i < 5; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(500); 
    digitalWrite(BUZZER_PIN, LOW);
    delay(500); 
  }
}

void triggerBuzzer2() {
  for (int i = 0; i < 7; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(333); 
    digitalWrite(BUZZER_PIN, LOW);
    delay(333); 
  }
}

void showWelcomeScreen() {
  tft.fillScreen(MED_BG);
  
  tft.drawRect(5, 5, 470, 310, MED_ACCENT);
  tft.drawRect(7, 7, 466, 306, MED_ACCENT);

  tft.setTextDatum(MC_DATUM);
  tft.setTextSize(1);

  tft.setTextColor(MED_OK, MED_BG);
  tft.drawString("PAGTULTOL", 240, 100, 4);

  tft.setTextColor(MED_TEXT, MED_BG);
  tft.drawString("Wireless Patient Monitor", 240, 140, 4);

  tft.setTextColor(MED_ACCENT, MED_BG);
  tft.drawString("Initializing System...", 240, 220, 2);

  tft.setTextDatum(TL_DATUM);
}

void showWarningScreen() {
  tft.fillScreen(MED_BG);
  
  tft.drawRect(5, 5, 470, 310, MED_ALERT);
  tft.drawRect(7, 7, 466, 306, MED_ALERT);

  tft.setTextDatum(MC_DATUM);
  tft.setTextSize(1);

  tft.setTextColor(MED_ALERT, MED_BG);
  tft.drawString("WARNING!!!", 240, 100, 4);

  tft.setTextColor(MED_TEXT, MED_BG);
  tft.drawString("The patient did not take the medicine", 240, 140, 4);

  tft.setTextDatum(TL_DATUM);
}

void drawMedicalInterface() {
  for (int i = 0; i < 480; i += 40) tft.drawFastVLine(i, 0, 320, MED_GRID);
  for (int i = 0; i < 320; i += 40) tft.drawFastHLine(0, i, 480, MED_GRID);

  tft.fillRect(0, 0, 480, 40, 0x10A2); 
  tft.setTextColor(MED_TEXT, 0x10A2);
  tft.setTextSize(2);
  tft.setCursor(10, 10);
  tft.print("PAGTULTOL RECEIVER  |  MONITOR-01");

  tft.setTextSize(1);

  tft.drawRect(20, 60, 140, 100, MED_ACCENT);
  tft.setTextColor(MED_ACCENT, MED_BG);
  tft.drawString("SYSTOLIC", 30, 70, 2);
  tft.setTextColor(MED_OK, MED_BG);
  tft.drawNumber(0, 50, 95, 6);
  
  tft.drawRect(20, 180, 140, 100, MED_ACCENT);
  tft.setTextColor(MED_ACCENT, MED_BG);
  tft.drawString("DIASTOLIC", 30, 190, 2);
  tft.setTextColor(0xFFE0, MED_BG); 
  tft.drawNumber(0, 50, 215, 6);

  tft.drawRect(180, 60, 180, 100, MED_ACCENT);
  tft.setTextColor(MED_ACCENT, MED_BG);
  tft.drawString("HEART RATE(BPM)", 190, 70, 2);
  tft.setTextColor(MED_OK, MED_BG);
  tft.drawNumber(0, 220, 95, 6);

  tft.drawRect(180, 180, 180, 100, MED_TEXT);
  tft.setTextColor(MED_ACCENT, MED_BG);
  tft.drawString("CLASSIFICATION", 190, 190, 2);
  tft.setTextColor(0xFFE0, MED_BG); 

  tft.drawFastHLine(0, 300, 480, MED_TEXT);
  updateStatus("INITIALIZING SYSTEM...", MED_ACCENT);
}

void setup() {
  Serial.begin(9600);
  
  pinMode(RX_LED_PIN, OUTPUT);
  digitalWrite(RX_LED_PIN, LOW);
  pinMode(BUZZER_PIN, OUTPUT);    
  digitalWrite(BUZZER_PIN, LOW);  
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, HIGH);
  pinMode(POWER_BTN_PIN, INPUT_PULLUP);

  tft.init();
  tft.setRotation(1);
  tft.fillScreen(MED_BG);
  
  showWelcomeScreen();
  delay(3000);
  tft.fillScreen(MED_BG);
  drawMedicalInterface();

  hspi = new SPIClass(HSPI);
  hspi->begin(HSPI_SCLK, HSPI_MISO, HSPI_MOSI, HSPI_SS);
  LoRa.setSPI(*hspi);
  LoRa.setPins(HSPI_SS, LORA_RST, LORA_DIO0);

  if (!LoRa.begin(433E6)) {
    Serial.println("LoRa Failed!");
    updateStatus("LORA ERROR", MED_ALERT);
  } else {
    LoRa.setSyncWord(0xF3);          
                                      
    LoRa.setTxPower(20);             
    LoRa.setSignalBandwidth(50E3);   
    LoRa.setSpreadingFactor(12);     
    LoRa.setCodingRate4(8);          
    LoRa.enableCrc();                
    
    updateStatus("SECURE LINK READY", MED_OK);
  }
}

void loop() {
  if (digitalRead(POWER_BTN_PIN) == LOW) {
    if (!isPressing) { isPressing = true; pressStartTime = millis(); }
    if (!hasToggled && (millis() - pressStartTime >= 3000)) {
      isSystemOn = !isSystemOn; hasToggled = true;
      if (isSystemOn) {
        tft.init(); tft.setRotation(1); tft.fillScreen(MED_BG);
        digitalWrite(TFT_BL, HIGH);
        
        showWelcomeScreen();
        delay(1500);
        tft.fillScreen(MED_BG);
        drawMedicalInterface();
        updateStatus("SYSTEM RESTORED", MED_OK);
      } else {
        tft.fillScreen(MED_BG); digitalWrite(TFT_BL, LOW);
        tft.writecommand(0x10); delay(100); tft.writecommand(0x28);
        digitalWrite(RX_LED_PIN, LOW);
      }
    }
  } else { isPressing = false; hasToggled = false; }

  if (!isSystemOn) return;

  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String loRaData = "";
    while (LoRa.available()) loRaData += (char)LoRa.read();
    
    Serial.println("RX: " + loRaData);

    if (loRaData == "START_SCAN") {
        digitalWrite(RX_LED_PIN, HIGH);
        updateStatus("MONITORING ACTIVE...", MED_ALERT);
        
        tft.setTextColor(MED_ALERT, MED_BG);
        tft.setTextSize(1);
    }
    else if (loRaData == "STOP_SCAN") {
        digitalWrite(RX_LED_PIN, LOW);
        updateStatus("ABORTED", MED_OK);
    }
    else if (loRaData == "NO") {
      showWarningScreen();
      for (int i = 0; i <= 20; i++) {
        digitalWrite(RX_LED_PIN, HIGH);
        digitalWrite(BUZZER_PIN, HIGH);
        delay(250);
        digitalWrite(RX_LED_PIN, LOW);
        digitalWrite(BUZZER_PIN, LOW);
        delay(250);
      }
      tft.fillScreen(MED_BG);
      drawMedicalInterface();
      updateStatus("SECURE LINK READY", MED_OK);
    }
    else {
        int commaIndex = loRaData.indexOf(", ");
        int commaIndex2 = loRaData.indexOf(", ", commaIndex + 1);
        String sys = loRaData.substring(0, commaIndex);      
        String dia = loRaData.substring(commaIndex + 1, commaIndex2);
        String bpm = loRaData.substring(commaIndex2 + 1);
        int sysValue = sys.toInt();
        int diaValue = dia.toInt();
        int bpmValue = bpm.toInt();

        tft.drawRect(20, 60, 140, 100, MED_ACCENT);
        tft.setTextColor(MED_ACCENT, MED_BG);
        tft.drawString("SYSTOLIC", 30, 70, 2);      
        tft.setTextColor(MED_OK, MED_BG);
        tft.drawNumber(sysValue, 50, 95, 6);

        tft.drawRect(20, 180, 140, 100, MED_ACCENT);
        tft.setTextColor(MED_ACCENT, MED_BG);
        tft.drawString("DIASTOLIC", 30, 190, 2);
        tft.setTextColor(0xFFE0, MED_BG); 
        tft.drawNumber(diaValue, 50, 215, 6);

        tft.drawRect(180, 60, 180, 100, MED_ACCENT);
        tft.setTextColor(MED_ACCENT, MED_BG);
        tft.drawString("HEART RATE(BPM)", 190, 70, 2);
        tft.setTextColor(MED_OK, MED_BG);
        tft.drawNumber(bpmValue, 220, 95, 6);
        digitalWrite(RX_LED_PIN, LOW);

        int Rssi = LoRa.packetRssi();
        String rssi = String(Rssi);
        updateStatus("Received Signal Strength: " + (rssi) + "dBm", MED_ALERT);
        
        if (sysValue < 120 && diaValue < 80) {
          tft.drawRect(180, 180, 180, 100, MED_TEXT);
          tft.setTextColor(MED_ACCENT, MED_BG);
          tft.drawString("CLASSIFICATION", 190, 190, 2);
          tft.setTextColor(MED_OK, MED_BG); 
          tft.drawString("OPTIMAL", 220, 230, 2);
          tft.setTextSize(1);
          triggerBuzzer();
        }
        else if ((sysValue >= 120 && sysValue <= 129) || (diaValue >= 80 && diaValue <= 84))  {
          tft.drawRect(180, 180, 180, 100, MED_TEXT);
          tft.setTextColor(MED_ACCENT, MED_BG);
          tft.drawString("CLASSIFICATION", 190, 190, 2);
          tft.setTextColor(MED_OK, MED_BG); 
          tft.drawString("NORMAL", 220, 230, 2);
          tft.setTextSize(1);
          triggerBuzzer();
        }
        else if ((sysValue >= 130 && sysValue <= 139) || (diaValue >= 85 && diaValue <= 89)) {
          tft.drawRect(180, 180, 180, 100, MED_TEXT);
          tft.setTextColor(MED_ACCENT, MED_BG);
          tft.drawString("CLASSIFICATION", 190, 190, 2);
          tft.setTextColor(MED_OK, MED_BG); 
          tft.drawString("HIGH NORMAL", 220, 230, 2);
          tft.setTextSize(1);
          triggerBuzzer();
        }
        else if ((sysValue >= 140 && sysValue <= 159) || (diaValue >= 90 && diaValue <= 99)) {
          tft.drawRect(180, 180, 180, 100, MED_TEXT);
          tft.setTextColor(MED_ACCENT, MED_BG);
          tft.drawString("CLASSIFICATION", 190, 190, 2);
          tft.setTextColor(MED_ALERT, MED_BG); 
          tft.drawString("GRADE 1 HYPERTENSION", 220, 230, 2);
          tft.setTextSize(1);
          triggerBuzzer2();
        }
        else if ((sysValue >= 160 && sysValue <= 179) || (diaValue >= 100 && diaValue <= 109)) {
          tft.drawRect(180, 180, 180, 100, MED_TEXT);
          tft.setTextColor(MED_ACCENT, MED_BG);
          tft.drawString("CLASSIFICATION", 190, 190, 2);
          tft.setTextColor(MED_ALERT, MED_BG); 
          tft.drawString("GRADE 2 HYPERTENSION", 220, 230, 2);
          tft.setTextSize(1);
          triggerBuzzer2();
        }
        else if (sysValue >= 180 || diaValue >= 110) {
          tft.drawRect(180, 180, 180, 100, MED_TEXT);
          tft.setTextColor(MED_ACCENT, MED_BG);
          tft.drawString("CLASSIFICATION", 190, 190, 2);
          tft.setTextColor(MED_ALERT, MED_BG); 
          tft.drawString("GRADE 3 HYPERTENSION", 220, 230, 2);
          tft.setTextSize(1);
          triggerBuzzer2();
        }
        else if (sysValue > 140 && diaValue < 90) {
          tft.drawRect(180, 180, 180, 100, MED_TEXT);
          tft.setTextColor(MED_ACCENT, MED_BG);
          tft.drawString("CLASSIFICATION", 190, 190, 2);
          tft.setTextColor(MED_ALERT, MED_BG); 
          tft.drawString("ISOLATED SYSTOLIC HYPERTENSION", 220, 230, 2);
          tft.setTextSize(1);
          triggerBuzzer2();
        }
    }
  }
}
