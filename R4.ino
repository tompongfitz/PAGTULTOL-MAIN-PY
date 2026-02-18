/* PAGTULTOL TRANSMITTER (ARDUINO UNO R4 WIFI)
   - Reads DS18B20
   - Sends LoRa (SF12)
   - Communicates with Python App via Serial
   - NO CLOUD / OFFLINE MODE
*/

#include <SPI.h>
#include <LoRa.h>
//#include <OneWire.h>
//#include <DallasTemperature.h>
#include "BP.h"

// ---------------------------------------------------------------------------
//  HARDWARE CONFIGURATION
// ---------------------------------------------------------------------------
//#define ONE_WIRE_BUS 4    // DS18B20 Pin
#define TX_LED_PIN   5    // Monitoring LED
#define BP_START_PIN 8
#define BUZZER 7

// LoRa Pins for Arduino UNO R4
#define LORA_SS      10
#define LORA_RST     9
#define LORA_DIO0    2

// ---------------------------------------------------------------------------
//  INITIALIZATION
// ---------------------------------------------------------------------------
// Initialize Hardware
//OneWire oneWire(ONE_WIRE_BUS);
//DallasTemperature sensors(&oneWire);


//void sendLoRaMessage(String message) {
//  LoRa.beginPacket();
//  LoRa.print(message);
//  if (LoRa.endPacket() == 0) {
//    // Silent fail
//  }
//}

void setup() {
  // 1. Initialize Serial (Communication with Python)
  Serial.begin(9600);
  delay(500);


  // 2. Initialize Hardware
  pinMode(BP_START_PIN, OUTPUT);  
  pinMode(TX_LED_PIN, OUTPUT);
  digitalWrite(BP_START_PIN, HIGH);
  digitalWrite(TX_LED_PIN, LOW);
  
  //sensors.begin();
  BP_init(); // Assuming this is defined in your "BP.h"
  delay(1500);


  // 3. Initialize LoRa
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
 
  if (!LoRa.begin(433E6)) {
    Serial.println("LoRa Init Failed!");
  } 
  else {
    // --- PRIVACY & RANGE SETTINGS ---
    LoRa.setSyncWord(0xF3);          // PRIVATE KEY: Must match Receiver!
    
    LoRa.setTxPower(20);             // Max Power
    LoRa.setSignalBandwidth(50E3);   // Match Receiver
    LoRa.setSpreadingFactor(12);     // Match Receiver
    LoRa.setCodingRate4(8);          // Match Receiver
    LoRa.enableCrc();
  }
}




void loop() {
  // 1. Read Temperature
  //sensors.requestTemperatures();
//  float tempC = sensors.getTempCByIndex(0);

  // Check valid reading (DS18B20 returns -127 if error)
//  if(tempC > -100 && tempC < 100) {
    
    // --- SEND TO PYTHON APP (USB) ---
//    Serial.println(tempC);

    // --- CHECK FOR PYTHON COMMANDS ---

    int s = bp_sys;
    int d = bp_dia;
    int p = bp_bpm;
    
    
    if (Serial.available() > 0) {
      String command = Serial.readStringUntil('\n');
      command.trim();
      
      if (command == "SEND") {
        LoRa.beginPacket();
        LoRa.print(bp_sys);
        LoRa.print(", ");
        LoRa.print(bp_dia);
        LoRa.print(", ");
        LoRa.print(bp_bpm);
        LoRa.endPacket();
        
        digitalWrite(TX_LED_PIN, LOW);
        digitalWrite(BP_START_PIN, LOW);
        delay(200);
        digitalWrite(BP_START_PIN, HIGH);
      }
      else if (command == "START") {
        LoRa.beginPacket();
        LoRa.print("START_SCAN");
        LoRa.endPacket();
        digitalWrite(TX_LED_PIN, HIGH);
        digitalWrite(BP_START_PIN, LOW);
        delay(200);
        digitalWrite(BP_START_PIN, HIGH);
        
      }
      else if (command == "STOP") {
        LoRa.beginPacket();
        LoRa.print("STOP_SCAN");
        LoRa.endPacket();
        digitalWrite(TX_LED_PIN, LOW);
        digitalWrite(BP_START_PIN, LOW);
        delay(200);
        digitalWrite(BP_START_PIN, HIGH);
        }
      else if (command == "BEEP") {
        digitalWrite(7, HIGH);
        delay(500);
        digitalWrite(7, LOW);
        delay(500);
        }
      }
   BP_getData(); 
}
