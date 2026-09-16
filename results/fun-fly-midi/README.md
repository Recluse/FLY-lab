# The fly plays music

A side amusement, and an honest one. Nothing here is a result; it reuses the
spike recordings from the main experiment as a source of numbers and turns them
into MIDI.

Listen first: [`fly-blues.mp3`](fly-blues.mp3) — one minute, rendered in FL
Studio from [`fly_blues.mid`](fly_blues.mid) with no editing of the notes.

## Where the notes come from

Every episode of the main experiment recorded, for each 15 ms tick, how many
spikes the left and right descending populations produced — the same two
numbers whose difference steered the body. Sixty episodes are used here: thirty
with the stimulus on the left, thirty with it on the right. That is 4,020 ticks,
or about 67 numbers per second, which is a sequencer written in the wrong
notation.

The third scenario, no stimulus at all, is thirty episodes of exactly zero
spikes. It is not included, though as a piece of conceptual music it is
flawless.

## Two programs

### `spikes_to_midi.py` — the raw transcription

One brain tick becomes one note. No musical rules at all: pitch is the
left-minus-right difference on a pentatonic scale, velocity is the total spike
count, and a kick marks the tick where the sensor fired.

```sh
python3 spikes_to_midi.py           # fly_spikes.mid — a tick is a 32nd at 125 BPM, four times slower than the fly
python3 spikes_to_midi.py --real    # fly_spikes_realtime.mid — a tick is 15 ms exactly: a 16th at 1000 BPM
python3 spikes_to_midi.py --check   # self-check only
```

The real-time version is the fly's actual decision rate, 67 notes per second.
It is unlistenable, which is the point.

### `fly_blues.py` — the same numbers under composition rules

A twelve-bar blues. The rules are human, the choices inside them are the fly's.

```sh
python3 fly_blues.py                # fly_blues.mid, plus a report on how much of it is really the fly
```

| Decided by the rules | Decided by the fly |
|---|---|
| Twelve-bar progression in A (I7–IV7–V7) | Play or stay silent: activity above the median |
| Swing: off-beats land a triplet late | Pitch: percentile of the left-minus-right difference |
| Walking bass in quarters on chord tones | Note length: long when activity runs high |
| Ride, hat, kick and snare on two and four | Velocity: total spike count |
| No melodic leap wider than four scale steps | Direction of the walking bass: sign of the difference |
| Strong beats must land on a chord tone | Which scale each chorus uses: its mean activity |
| The four scales on offer | |

Each eighth note aggregates 20 brain ticks, 300 ms of model time.

## How much of it is actually the fly

The script prints this, because without it the whole thing would be decoration:

```
fly_blues.mid: 25 bars, 124 melody notes, 1066 events, 60 s
  scales per chorus: dorian, minor pentatonic
  fly's raw pitch survived the rules in 93/124 notes (75%); 3 clamped for leaps, 28 snapped to chord tones
```

Three quarters of the melody is the fly's own choice of pitch; the rest was
pulled into key by the rules. A rule set tight enough to guarantee pretty music
would leave nothing of the fly in it, and this number is what makes that
trade-off visible instead of rhetorical.

One accident worth keeping: the first chorus is built from the left-stimulus
episodes and the second from the right-stimulus ones, and because a
right-side stimulus produces less descending activity (mean 58 spikes per
window against 93 on the left), the fly chose different scales for them —
dorian and then minor pentatonic. It changes mode exactly when the stimulus
changes side.

## Changing the rules

Everything is a constant at the top of `fly_blues.py`:

- `PROGRESSION` — one chord root per bar, in semitones from the key. The
  default is the canonical twelve-bar blues; any list works, and
  `BARS_PER_CHORUS` must match its length.
- `SCALES` — the menu the fly picks from, as semitone offsets. Add your own;
  the choice per chorus is made by mean activity, so the order matters (quiet
  choruses take the first entries).
- `KEY`, `MELODY_OCTAVE`, `BASS_OCTAVE` — where it all sits. `KEY = 9` is A.
- `TEMPO_US` — microseconds per quarter note; 600,000 is 100 BPM.
- `SWING` — how late the off-beats land. Zero for a straight feel.
- `TICKS_PER_STEP` — how many 15 ms brain ticks make one eighth note. Lower it
  and the fly plays faster and jumpier; raise it and it smooths out.
- `MAX_LEAP` — the widest melodic leap allowed, in scale steps. Raise it to let
  more of the fly through at the cost of singable lines; the printed
  "survived the rules" figure will move with it.
- The instruments are the program-change bytes in `build`: `\xc0\x42` is a
  tenor sax for the melody, `\xc1\x20` an acoustic bass.

Both scripts write MIDI by hand — no library needed. Run either with `--check`
to execute its self-checks alone; they cover the variable-length encoder, the
scale arithmetic and the aggregation window, which is where a silent corruption
would come from.
