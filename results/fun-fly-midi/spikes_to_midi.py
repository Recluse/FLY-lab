"""Turn recorded descending-neuron spikes into a MIDI file.

One brain tick is 15 ms of model time and becomes one 32nd note at 125 BPM,
so the result runs four times slower than the fly did. Nothing here is a
result: the scale, the tempo and the instruments are human choices, the fly
only supplies the numbers.

    python3 spikes_to_midi.py            # writes fly_spikes.mid
    python3 spikes_to_midi.py --check    # self-check only
"""
import csv
import glob
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PPQ = 96
STEP = PPQ // 8                      # a 32nd note
TEMPO_US = 480_000                   # 125 BPM
# "--real" plays one tick per 15 ms, the speed the fly actually ran at: a 16th
# note at 1000 BPM. It is unlistenable, which is the point.
REAL = (PPQ // 4, 60_000)
PENTATONIC = (0, 3, 5, 7, 10)
MELODY_ROOT, BASS_ROOT = 69, 33      # A4 and A1
KICK, HAT = 36, 42


def varlen(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def degree(index):
    return 12 * (index // len(PENTATONIC)) + PENTATONIC[index % len(PENTATONIC)]


def read(scenario):
    ticks = []
    for run in sorted(glob.glob(str(ROOT / f"results/cd-test-v1-{scenario}-C-*/trajectory.csv"))):
        for row in csv.DictReader(open(run)):
            ticks.append((int(row["brain_dn_left"]), int(row["brain_dn_right"]),
                          float(row["sensor_left"]) > 0.5 or float(row["sensor_right"]) > 0.5))
    return ticks


def voice(ticks, sign, root, channel, span, events):
    """One note per tick while the population difference has the expected sign."""
    peak = max((sign * (l - r) for l, r, _ in ticks), default=1) or 1
    for k, (left, right, _) in enumerate(ticks):
        value = sign * (left - right)
        if value <= 0:
            continue
        note = root + degree(round(value / peak * span))
        velocity = 40 + int(80 * min(1.0, (left + right) / 120))
        at = k * STEP
        events.append((at, 0x90 | channel, note, velocity))
        events.append((at + STEP - 1, 0x80 | channel, note, 0))


def drums(ticks, events):
    was_on = False
    for k, (_, _, stimulus) in enumerate(ticks):
        at = k * STEP
        if stimulus and not was_on:
            events.append((at, 0x99, KICK, 110))
            events.append((at + STEP, 0x89, KICK, 0))
        elif stimulus and k % 4 == 0:
            events.append((at, 0x99, HAT, 64))
            events.append((at + STEP - 1, 0x89, HAT, 0))
        was_on = stimulus


def track(events, name=b"", head=b""):
    body = bytearray()
    if name:
        body += b"\x00\xff\x03" + varlen(len(name)) + name
    body += head
    previous = 0
    for at, status, data1, data2 in sorted(events, key=lambda e: (e[0], e[1] & 0xF0)):
        body += varlen(at - previous) + bytes([status, data1, data2])
        previous = at
    body += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def build(out):
    left, right = read("left"), read("right")
    ticks = max(len(left), len(right))
    melody, bass, beat = [], [], []
    voice(left, +1, MELODY_ROOT, 0, 14, melody)
    voice(right, -1, BASS_ROOT, 1, 9, bass)
    drums(left, beat)
    events = melody + bass + beat
    tempo = track([], b"fly spikes", b"\x00\xff\x51\x03" + TEMPO_US.to_bytes(3, "big"))
    chunks = [tempo,
              track(melody, b"left descending", b"\x00\xc0\x51"),   # sawtooth lead
              track(bass, b"right descending", b"\x00\xc1\x26"),    # synth bass
              track(beat, b"stimulus")]
    out.write_bytes(b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), PPQ) + b"".join(chunks))
    seconds = ticks * STEP / PPQ * TEMPO_US / 1e6
    print(f"{out.name}: {ticks} ticks, {len(events)} events, {seconds:.0f} s")


def check():
    assert varlen(0) == b"\x00" and varlen(127) == b"\x7f"
    assert varlen(128) == b"\x81\x00" and varlen(0x3FFF) == b"\xff\x7f"
    assert degree(0) == 0 and degree(5) == 12 and degree(6) == 15
    assert read("none") and all(l == r == 0 for l, r, _ in read("none")), "silent scenario"
    print("checks passed")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        check()
        here = Path(__file__).resolve().parent
        if "--real" in sys.argv:
            globals()["STEP"], globals()["TEMPO_US"] = REAL
            build(here / "fly_spikes_realtime.mid")
        else:
            build(here / "fly_spikes.mid")
