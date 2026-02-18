 #include <Wire.h>
#define I2C_DEV_ADDR 0x50


volatile uint32_t i = 0;


// ISR: Master requests data
void onRequest() {
  Wire.print(i++);
  Wire.print(" Packets.");
}


// Data Parsing Variables
char bp_data[32];
volatile int bp_data_cnt = 0;
volatile bool bpcpy = 0;


volatile int bp_sys = 0;
volatile int bp_dia = 0;
volatile int bp_bpm = 0;
volatile int BP_final = 0;


// DEBUGGING VARIABLES
volatile int raw_buffer[10];
volatile int raw_len = 0;
volatile bool raw_ready = false;


// ISR: Master sends data (Receive Event)
void BP(int v) {
  // Reset raw buffer counter for this packet
  int temp_len = 0;
 
  while (Wire.available()) {
    char c = Wire.read();
   
    // --- 1. CAPTURE RAW DATA FOR DEBUGGING ---
    if (temp_len < 10) {
      raw_buffer[temp_len] = (int)c; // Store as integer to see value
      temp_len++;
    }


    // --- 2. EXISTING PARSING LOGIC ---
    // Check for Header '0' (ASCII 48)
    if (c == 48) {
      bpcpy = 1;
      bp_data_cnt = 0;
    }
   
    if (bpcpy) {
      bp_data[bp_data_cnt] = c;
      bp_data_cnt++;
     
      // Expected Packet: [Header, Sys, Dia, Pulse, ...]
      if (bp_data_cnt >= 5) {
        bp_sys = bp_data[1];
        bp_dia = bp_data[2];
        bp_bpm = bp_data[3];
       
        bpcpy = 0;
        bp_data_cnt = 0;
       
        // Removed the "> 60" filter so you can see ANY data arriving
        BP_final = 1;
      }
    }
  }
  // Signal main loop that raw data arrived
  raw_len = temp_len;
  raw_ready = true;
}


void BP_init(){
  Wire.onReceive(BP);
  Wire.onRequest(onRequest);
  Wire.begin((uint8_t)I2C_DEV_ADDR);
}


// Called in the main loop
void BP_getData() {
  // --- PRINT RAW DATA IF AVAILABLE ---
  // E comment ni Sir kay naka tokenize ang data bcn dli ma read sa App
  /*
  if (raw_ready) {
    Serial.print("DEBUG RAW: ");
    for (int k = 0; k < raw_len; k++) {
      Serial.print(raw_buffer[k]);
      Serial.print(" ");
    }
    Serial.println();
    raw_ready = false; // Reset flag
  }
  */

  // --- PRINT PARSED DATA IF VALID ---
  if (BP_final) {
    int s = bp_sys;
    int d = bp_dia;
    int p = bp_bpm;
   
    char tmpX[64];
    // Format: SYS=DIA=BPM
    sprintf(tmpX, "%d=%d=%d", s, d, p);
    Serial.println(tmpX);
   
    BP_final = 0;
  }
}
