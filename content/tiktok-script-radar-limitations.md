# TikTok Script: Why Cheap Doppler Radars Don't Work for Golf

## Hook (0-3 seconds)
"I tried doubling my amplifiers and it made things WORSE. Here's why cheap radar modules won't work for a DIY launch monitor."

---

## Part 1: The Problem (3-20 seconds)

"So I'm building a DIY golf launch monitor using a $5 Doppler radar - the CDM324. It works by bouncing microwaves off moving objects and measuring the frequency shift.

The problem? The signal coming out of this thing is measured in *microvolts*. That's millionths of a volt. Way too weak for any microcontroller to read."

---

## Part 2: The Attempted Solution (20-35 seconds)

"So I added an LM358 op-amp to boost the signal - that's what everyone online recommends. Got about 3 feet of range. Not great.

Then I thought - why not chain TWO amplifiers together? Double the gain, double the range, right?

Wrong. Here's what actually happened..."

---

## Part 3: Why Double Amp Failed (35-55 seconds)

"When I added the second amplifier, my noise floor went from 4,000 to 31,000. That's not a typo - almost 8x more noise.

See, amplifiers don't just boost your signal - they boost EVERYTHING. The electrical noise from your power supply, interference from the Pi, even the thermal noise from the components themselves.

I was amplifying garbage along with my signal. The golf ball signal was still buried in noise, just at a higher volume."

---

## Part 4: The Real Problem (55-75 seconds)

"But here's the thing I finally realized - even with perfect amplification, these cheap radar modules just aren't designed for this.

The CDM324 and HB100 are meant for detecting if a person walked through a doorway - not tracking a golf ball moving 150 miles per hour, 10 feet away.

They have:
- Wide, unfocused beams that scatter energy everywhere
- No built-in filtering for the specific frequencies we need
- Antenna designs optimized for presence detection, not speed measurement"

---

## Part 5: What Actually Works (75-90 seconds)

"Commercial launch monitors use purpose-built radar modules with:
- Narrow, focused beams
- Integrated amplifiers tuned for Doppler frequencies
- Proper filtering and signal processing

The closest thing for DIY? The OmniPreSense OPS243 - but it's $224, not $5.

Sometimes the cheap way is just... the cheap way. Back to the drawing board."

---

## Closing (90-95 seconds)

"Follow along as I figure out whether to build a proper amplifier circuit or bite the bullet on better hardware. Link in bio for the full project."

---

## On-Screen Text Suggestions

- "DIY Launch Monitor: Part X"
- "CDM324 radar: $5"
- "Signal output: ~10 microvolts"
- "Noise floor: 4,000 → 31,000"
- "OPS243: $224"
- "github.com/[your-repo]"

---

## B-Roll / Visual Suggestions

1. Close-up of the CDM324 module
2. Wiring on breadboard with dual LM358s
3. Terminal output showing the noise floor numbers
4. Side-by-side: cheap module vs OPS243 (image from their website)
5. Diagram of signal vs noise (see svg files)

---

## Key Talking Points If Condensing

If you need to trim this down, the core message is:

1. Cheap radar = microvolt output (too weak)
2. Adding amps = amplifies noise too
3. These modules aren't designed for speed tracking
4. Real solution = purpose-built hardware ($$$)

---

## Hashtags

#DIY #GolfTech #LaunchMonitor #Trackman #RaspberryPi #Electronics #Doppler #Radar #GolfTikTok #Maker #Engineering #OpenSource
