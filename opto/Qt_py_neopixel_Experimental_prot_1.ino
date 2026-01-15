#include <Adafruit_NeoPixel.h>
#include <elapsedMillis.h>

// How many internal neopixels do we have? some boards have more than one!
#define NUMPIXELS        40

int pin_neo = 28;

//Adafruit_NeoPixel pixels(NUMPIXELS, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);

Adafruit_NeoPixel pixels(NUMPIXELS, pin_neo, NEO_GRBW + NEO_KHZ800);

unsigned long first_delay = 120000; //120 seconds
unsigned long delay_ = 12000;
bool state = LOW;

elapsedMillis timeElapsed;
unsigned long previousMillis;
byte max_intensity = 255;
byte N_cycles = 0;
byte N = 3;

// the setup routine runs once when you press reset:
void setup() {
  Serial.begin(115200);

#if defined(NEOPIXEL_POWER)
  // If this board has a power control pin, we must set it to output and high
  // in order to enable the NeoPixels. We put this in an #if defined so it can
  // be reused for other boards without compilation errors
  pinMode(NEOPIXEL_POWER, OUTPUT);
  digitalWrite(NEOPIXEL_POWER, HIGH);
#endif

  pixels.begin(); // INITIALIZE NeoPixel strip object (REQUIRED)
  pixels.setBrightness(max_intensity); // not so bright
}

// the loop routine runs over and over again forever:
void loop() 
{
    blinking(first_delay, delay_);
}

  void blinking(unsigned int interval_low, unsigned int interval)
  {
  unsigned long currentMillis = millis(); 
     
    // set color to green
    pixels.fill(0x00FF00);
    pixels.show();

    while (N_cycles > N) 
    {
       //set color to green + blue
       pixels.fill(0x00FFFF);
       pixels.show();
    }
  
  // Print intensity 0
  //Serial.println(state);
//  Serial.print(" ");
//  Serial.println(millis());

  while (currentMillis > interval_low && N_cycles <= N)
  {
    unsigned long currentMillis = millis();

    
    if (currentMillis - previousMillis >= interval && N_cycles <= N) 
    {
      // save the last time you blinked the LED
      previousMillis = currentMillis;
  
      // if the state is off turn it on and vice-versa:
      if (state == LOW) 
        {
          state = HIGH;
          // set color to green + blue
          pixels.fill(0x00FFFF);
          pixels.show();
        } 
      else 
        {
          state = LOW;
          // set color to green
          pixels.fill(0x00FF00);
          pixels.show();
          N_cycles++;
          Serial.println(N_cycles);
        }
        //Serial.println(state);
        Serial.println(N_cycles);
//        Serial.print(" ");
//        Serial.println(millis());
      }

      //Serial.println(N_cycles);
      //Serial.println(state);
//      Serial.print(" ");
//      Serial.println(millis());
    }
  }
