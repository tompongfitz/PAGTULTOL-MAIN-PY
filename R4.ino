#include <SPI.h>
#include <LoRa.h>
#include "BP.h"
#include "Bonezegei_ULN2003_Stepper.h"

#define TX_LED_PIN   5
#define BP_START_PIN 8
#define BUZZER 7

#define LORA_SS      10
#define LORA_RST     9
#define LORA_DIO0    2

#define FORWARD 1
#define REVERSE 0

Bonezegei_ULN2003_Stepper Stepper(0, 1, 2, 4);

bool isAlarmActive = false;
unsigned long previousBuzzerMillis = 0;
bool buzzerState = LOW;

void setup() {
  Stepper.begin();
  Stepper.setSpeed(5);
  
  Serial.begin(9600);
  delay(500);

  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);
  pinMode(BP_START_PIN, OUTPUT);  
  pinMode(TX_LED_PIN, OUTPUT);
  digitalWrite(BP_START_PIN, HIGH);
  digitalWrite(TX_LED_PIN, LOW);
  
  BP_init(); 
  delay(1500);

  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  
  if (!LoRa.begin(433E6)) {
    Serial.println("LoRa Init Failed!");
  } 
  else {
    LoRa.setSyncWord(0xF3);
    
    LoRa.setTxPower(20);
    LoRa.setSignalBandwidth(50E3);
    LoRa.setSpreadingFactor(12);
    LoRa.setCodingRate4(8);
    LoRa.enableCrc();
  }
}

void loop() {
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
        digitalWrite(
