"""The fly plays a twelve-bar blues, under rules it did not choose.

The rules are mine: the progression, the swing, the scales, the walking bass,
the drum pattern, and every constraint that keeps a note in key. The fly
supplies four decisions per eighth note — whether to play, how high, how hard,
how long — from the spikes its descending populations produced while it was
steering a body around an arena.

Because the rules do most of the work, the script also reports how often the
fly's raw choice survived them. That number is the honest part.

    python3 fly_blues.py             # writes fly_blues.mid
    python3 fly_blues.py --shuffle   # the same numbers with their order destroyed
    python3 fly_blues.py --check     # self-check only
"""
import random
import statistics as st
import struct
import sys
from pathlib import Path

from spikes_to_midi import PPQ, read, track

TEMPO_US = 600_000                        # 100 BPM
EIGHTH = PPQ // 2
SWING = EIGHTH // 3                       # off-beats land late, triplet feel
TICKS_PER_STEP = 20                       # 20 brain ticks (300 ms) per eighth
BARS_PER_CHORUS, STEPS_PER_BAR = 12, 8

# Twelve-bar blues in A, one chord per bar.
PROGRESSION = [0, 0, 0, 0, 5, 5, 0, 0, 7, 5, 0, 7]
SEVENTH = (0, 4, 7, 10)
SCALES = {
    "blues": (0, 3, 5, 6, 7, 10),
    "minor pentatonic": (0, 3, 5, 7, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
}
KEY, MELODY_OCTAVE, BASS_OCTAVE = 9, 60, 36   # A, and the octaves to sit in
KICK, SNARE, HAT, RIDE = 36, 38, 42, 51
MAX_LEAP = 4                              # scale steps between consecutive notes


def pitch(scale, index, base):
    return base + KEY + 12 * (index // len(scale)) + scale[index % len(scale)]


def nearest_chord_tone(scale, index, root, base):
    """Snap a scale degree to the closest tone of the current chord."""
    want = pitch(scale, index, base)
    candidates = [base + KEY + root + t + 12 * o for t in SEVENTH for o in (0, 1, 2)]
    return min(candidates, key=lambda n: (abs(n - want), n))


def windows(ticks, per_step):
    for k in range(len(ticks) // per_step):
        chunk = ticks[k * per_step:(k + 1) * per_step]
        left = [l for l, _, _ in chunk]
        right = [r for _, r, _ in chunk]
        yield st.mean(l - r for l, r in zip(left, right)), st.mean(l + r for l, r in zip(left, right))


def rank(values):
    """Percentile of each value within its own distribution, 0..1."""
    order = sorted(values)
    return [order.index(v) / max(1, len(order) - 1) for v in values]


def melody(steps, events, report):
    span = len(SCALES["blues"]) * 2 - 1
    heights = rank([d for d, _ in steps])
    loudness = rank([a for _, a in steps])
    gate = st.median([a for _, a in steps])
    previous = None
    for k, ((_, activity), height, loud) in enumerate(zip(steps, heights, loudness)):
        bar, beat = divmod(k, STEPS_PER_BAR)
        chorus, bar_in_chorus = divmod(bar, BARS_PER_CHORUS)
        scale = SCALES[report["scales"][chorus % len(report["scales"])]]
        strong = beat in (0, 4)
        if activity <= gate and not strong:
            continue                                   # the fly chose silence
        report["notes"] += 1
        wanted = round(height * (len(scale) * 2 - 1))
        index = wanted
        if previous is not None and abs(index - previous) > MAX_LEAP:
            index = previous + MAX_LEAP * (1 if index > previous else -1)
            report["leap_clamped"] += 1
        note = pitch(scale, min(index, span), MELODY_OCTAVE)
        if strong:
            snapped = nearest_chord_tone(scale, min(index, span),
                                         PROGRESSION[bar_in_chorus], MELODY_OCTAVE)
            if snapped != note:
                report["snapped"] += 1
            note = snapped
        previous = index
        at = k * EIGHTH + (SWING if beat % 2 else 0)
        length = EIGHTH * 2 if activity > gate * 1.6 else EIGHTH
        velocity = 55 + int(45 * loud) + (10 if beat == 0 else 0)
        events.append((at, 0x90, note, min(velocity, 127)))
        events.append((at + length - 2, 0x80, note, 0))


def bass(steps, events):
    """Walking quarters on chord tones; the fly picks the direction."""
    for quarter in range(len(steps) // 2):
        bar, beat = divmod(quarter, 4)
        root = PROGRESSION[(bar % (len(PROGRESSION))) % BARS_PER_CHORUS]
        rising = steps[quarter * 2][0] >= 0
        degrees = (0, 4, 7, 10) if rising else (10, 7, 4, 0)
        note = BASS_OCTAVE + KEY + root + degrees[beat]
        at = quarter * EIGHTH * 2
        events.append((at, 0x91, note, 78))
        events.append((at + EIGHTH * 2 - 3, 0x81, note, 0))


def drums(steps, events):
    loud = rank([a for _, a in steps])
    for k, level in enumerate(loud):
        bar, beat = divmod(k, STEPS_PER_BAR)
        at = k * EIGHTH + (SWING if beat % 2 else 0)
        events.append((at, 0x99, RIDE if beat % 2 == 0 else HAT, 58 + int(20 * level)))
        events.append((at + EIGHTH // 2, 0x89, RIDE if beat % 2 == 0 else HAT, 0))
        if beat in (0, 6) or (beat == 3 and level > 0.8):
            events.append((at, 0x99, KICK, 100))
            events.append((at + EIGHTH // 2, 0x89, KICK, 0))
        if beat in (2, 6):
            events.append((at, 0x99, SNARE, 96))
            events.append((at + EIGHTH // 2, 0x89, SNARE, 0))
        if bar % 4 == 3 and beat >= 6 and level > 0.7:          # fill
            events.append((at + EIGHTH // 2, 0x99, SNARE, 110))
            events.append((at + EIGHTH - 2, 0x89, SNARE, 0))


def build(out, shuffle=False):
    ticks = read("left") + read("right")
    steps = list(windows(ticks, TICKS_PER_STEP))
    if shuffle:
        # Control arm: the same numbers, their order destroyed. Same
        # distribution of pitches and loudness, no temporal structure. If this
        # sounds as intentional as the real one, the fly's timing contributed
        # nothing and the rules are doing all the work.
        random.Random(0).shuffle(steps)
    bars = len(steps) // STEPS_PER_BAR
    steps = steps[:bars * STEPS_PER_BAR]
    names = list(SCALES)
    # The fly picks the scale for each chorus, from its own mean activity.
    choruses = max(1, bars // BARS_PER_CHORUS)
    quiet = min(a for _, a in steps)
    loudest = max(a for _, a in steps)
    chosen = []
    for c in range(choruses):
        window = steps[c * BARS_PER_CHORUS * STEPS_PER_BAR:(c + 1) * BARS_PER_CHORUS * STEPS_PER_BAR]
        level = st.mean(a for _, a in window) if window else quiet
        share = (level - quiet) / max(1e-9, loudest - quiet)
        chosen.append(names[min(int(share * len(names)), len(names) - 1)])
    report = {"notes": 0, "leap_clamped": 0, "snapped": 0, "scales": chosen}

    lead, low, beat = [], [], []
    melody(steps, lead, report)
    bass(steps, low)
    drums(steps, beat)
    chunks = [
        track([], b"fly blues", b"\x00\xff\x51\x03" + TEMPO_US.to_bytes(3, "big")),
        track(lead, b"melody - fly", b"\x00\xc0\x42"),      # tenor sax
        track(low, b"walking bass", b"\x00\xc1\x20"),
        track(beat, b"drums"),
    ]
    out.write_bytes(b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), PPQ) + b"".join(chunks))
    kept = report["notes"] - report["leap_clamped"] - report["snapped"]
    print(f"{out.name}: {bars} bars, {report['notes']} melody notes, "
          f"{len(lead) + len(low) + len(beat)} events, "
          f"{bars * 4 * TEMPO_US / 1e6:.0f} s")
    print(f"  scales per chorus: {', '.join(chosen)}")
    print(f"  fly's raw pitch survived the rules in {kept}/{report['notes']} notes "
          f"({100 * kept / max(1, report['notes']):.0f}%); "
          f"{report['leap_clamped']} clamped for leaps, {report['snapped']} snapped to chord tones")


def check():
    scale = SCALES["blues"]
    assert pitch(scale, 0, 60) == 69 and pitch(scale, 6, 60) == 81        # octave up
    assert nearest_chord_tone(scale, 0, 0, 60) == 69                      # A over A7
    assert len(PROGRESSION) == BARS_PER_CHORUS
    assert rank([5, 1, 3]) == [1.0, 0.0, 0.5]
    made_up = [(10, 0, False), (0, 10, True)] * 10
    assert len(list(windows(made_up, 20))) == 1
    print("checks passed")


if __name__ == "__main__":
    check()
    here = Path(__file__).resolve().parent
    if "--check" in sys.argv:
        pass
    elif "--shuffle" in sys.argv:
        build(here / "fly_blues_shuffled.mid", shuffle=True)
    else:
        build(here / "fly_blues.mid")
